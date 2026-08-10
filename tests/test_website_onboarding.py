from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.discovery import CrawlJob
from app.models.onboarding import WebsiteOnboarding, WebsiteOwnershipVerification
from app.models.website import Website
from app.schemas.onboarding import WebsiteOnboardingStart
from app.services.http_crawler import FetchResult
from app.services.website_onboarding import (
    VERIFICATION_PATH,
    check_website_ownership,
    renew_website_verification_file,
    start_website_onboarding,
    token_hash,
)


def _client(db):  # type: ignore[no-untyped-def]
    client = Client(name=f"Onboarding client {uuid4()}")
    db.add(client)
    db.flush()
    return client


def _payload(request_id=None):  # type: ignore[no-untyped-def]
    return WebsiteOnboardingStart(
        request_id=request_id or uuid4(),
        website_name="Fresh website",
        base_url="https://fresh.example.test/",
        settings={"sitemap_urls": ["https://fresh.example.test/sitemap.xml"]},
    )


def test_onboarding_requires_https() -> None:
    with pytest.raises(ValidationError, match="vereist HTTPS"):
        WebsiteOnboardingStart(
            request_id=uuid4(),
            website_name="Unsafe website",
            base_url="http://fresh.example.test/",
        )


def test_start_is_idempotent_persists_hash_and_never_starts_crawl() -> None:
    with SessionLocal() as db:
        client = _client(db)
        payload = _payload()

        first = start_website_onboarding(
            db, client_id=client.id, actor_user_id=None, payload=payload
        )
        repeated = start_website_onboarding(
            db, client_id=client.id, actor_user_id=None, payload=payload
        )

        assert first.id == repeated.id
        assert first.verification_file_content is not None
        assert repeated.verification_file_content is None
        assert first.status == "verification_pending"
        assert first.verification_path == VERIFICATION_PATH
        assert db.scalar(select(func.count()).select_from(Website)) == 1
        assert db.scalar(select(func.count()).select_from(WebsiteOnboarding)) == 1
        assert db.scalar(select(func.count()).select_from(CrawlJob)) == 0
        verification = db.scalar(select(WebsiteOwnershipVerification))
        assert verification is not None
        token = first.verification_file_content.split("=", 1)[1]
        assert verification.token_hash == token_hash(token)
        assert token not in verification.token_hash


def test_correct_file_verifies_website_and_advances_without_crawl(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    with SessionLocal() as db:
        client = _client(db)
        started = start_website_onboarding(
            db, client_id=client.id, actor_user_id=None, payload=_payload()
        )
        content = started.verification_file_content.encode()  # type: ignore[union-attr]
        target = f"https://fresh.example.test{VERIFICATION_PATH}"
        monkeypatch.setattr(
            "app.services.website_onboarding.fetch_url",
            lambda *_args, **_kwargs: FetchResult(
                requested_url=target,
                final_url=target,
                status_code=200,
                redirect_chain=[],
                headers={"content-type": "text/plain"},
                content=content,
                response_time_ms=1,
                response_size=len(content),
            ),
        )

        onboarding, verification = check_website_ownership(db, started.id)

        assert onboarding.status == "verified"
        assert onboarding.current_step == "crawl_preferences"
        assert verification.status == "verified"
        assert verification.attempt_count == 1
        assert db.scalar(select(func.count()).select_from(CrawlJob)) == 0
        assert db.get(Website, started.website_id).status == "active"  # type: ignore[union-attr]


def test_wrong_file_and_cross_origin_redirect_are_recoverable(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    with SessionLocal() as db:
        client = _client(db)
        started = start_website_onboarding(
            db, client_id=client.id, actor_user_id=None, payload=_payload()
        )
        responses = iter(
            [
                FetchResult(
                    requested_url="https://fresh.example.test/.well-known/x",
                    final_url=f"https://fresh.example.test{VERIFICATION_PATH}",
                    status_code=200,
                    redirect_chain=[],
                    headers={},
                    content=b"wrong",
                    response_time_ms=1,
                    response_size=5,
                ),
                FetchResult(
                    requested_url="https://fresh.example.test/.well-known/x",
                    final_url=f"https://outside.example.test{VERIFICATION_PATH}",
                    status_code=200,
                    redirect_chain=[],
                    headers={},
                    content=started.verification_file_content.encode(),  # type: ignore[union-attr]
                    response_time_ms=1,
                    response_size=10,
                ),
            ]
        )
        monkeypatch.setattr(
            "app.services.website_onboarding.fetch_url",
            lambda *_args, **_kwargs: next(responses),
        )

        first, verification = check_website_ownership(db, started.id)
        assert first.last_error_code == "verification_token_mismatch"
        second, verification = check_website_ownership(db, started.id)
        assert second.last_error_code == "verification_redirect_outside_scope"
        assert verification.status == "pending"
        assert verification.attempt_count == 2


def test_expired_verification_does_not_fetch(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    with SessionLocal() as db:
        client = _client(db)
        started = start_website_onboarding(
            db, client_id=client.id, actor_user_id=None, payload=_payload()
        )
        verification = db.scalar(select(WebsiteOwnershipVerification))
        assert verification is not None
        verification.expires_at = datetime(2020, 1, 1, tzinfo=UTC)
        db.commit()
        monkeypatch.setattr(
            "app.services.website_onboarding.fetch_url",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not fetch")),
        )

        onboarding, verification = check_website_ownership(db, started.id)

        assert onboarding.last_error_code == "verification_expired"
        assert verification.status == "expired"


def test_onboarding_api_starts_and_resumes_without_exposing_token_again(client) -> None:  # type: ignore[no-untyped-def]
    customer = client.post("/api/v1/clients", json={"name": "API onboarding client"}).json()
    request_id = str(uuid4())

    started = client.post(
        f"/api/v1/website-onboarding/clients/{customer['id']}",
        json={
            "request_id": request_id,
            "website_name": "Fresh API website",
            "base_url": "https://api-fresh.example.test/",
        },
    )
    repeated = client.post(
        f"/api/v1/website-onboarding/clients/{customer['id']}",
        json={
            "request_id": request_id,
            "website_name": "Fresh API website",
            "base_url": "https://api-fresh.example.test/",
        },
    )

    assert started.status_code == 201
    assert started.json()["verification_file_content"].startswith("thactual-site-verification=")
    assert repeated.status_code == 201
    assert repeated.json()["id"] == started.json()["id"]
    assert repeated.json()["verification_file_content"] is None
    resumed = client.get(f"/api/v1/website-onboarding/{started.json()['id']}")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "verification_pending"
    assert resumed.json()["verification_file_content"] is None


def test_renewed_verification_file_replaces_hash_and_resets_attempts() -> None:
    with SessionLocal() as db:
        client = _client(db)
        started = start_website_onboarding(
            db, client_id=client.id, actor_user_id=None, payload=_payload()
        )
        verification = db.scalar(
            select(WebsiteOwnershipVerification).where(
                WebsiteOwnershipVerification.onboarding_id == started.id
            )
        )
        assert verification is not None
        previous_hash = verification.token_hash
        verification.status = "expired"
        verification.attempt_count = 4
        db.commit()

        content = renew_website_verification_file(db, started.id, actor_user_id=None)

        db.refresh(verification)
        assert content.startswith("thactual-site-verification=")
        renewed_token = content.removeprefix("thactual-site-verification=")
        assert token_hash(renewed_token) == verification.token_hash
        assert verification.token_hash != previous_hash
        assert verification.status == "pending"
        assert verification.attempt_count == 0


def test_verification_file_download_is_not_cached_and_rotates_token(client) -> None:  # type: ignore[no-untyped-def]
    customer = client.post("/api/v1/clients", json={"name": "Download onboarding client"}).json()
    started = client.post(
        f"/api/v1/website-onboarding/clients/{customer['id']}",
        json={
            "request_id": str(uuid4()),
            "website_name": "Download website",
            "base_url": "https://download.example.test/",
        },
    ).json()

    response = client.post(f"/api/v1/website-onboarding/{started['id']}/verification/file")

    assert response.status_code == 200
    assert response.text.startswith("thactual-site-verification=")
    assert response.headers["cache-control"] == "no-store"
    assert 'filename="thactual-verification.txt"' in response.headers["content-disposition"]
    assert (
        client.get(f"/api/v1/website-onboarding/{started['id']}").json()[
            "verification_file_content"
        ]
        is None
    )

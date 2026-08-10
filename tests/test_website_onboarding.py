from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun
from app.models.discovery import CrawlJob
from app.models.onboarding import WebsiteOnboarding, WebsiteOwnershipVerification
from app.models.website import Website
from app.schemas.onboarding import WebsiteOnboardingCrawlPreferences, WebsiteOnboardingStart
from app.services.http_crawler import FetchResult
from app.services.website_onboarding import (
    VERIFICATION_PATH,
    check_website_ownership,
    get_website_onboarding,
    renew_website_verification_file,
    retry_first_onboarding_crawl,
    start_first_onboarding_crawl,
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


def test_first_crawl_requires_verification_and_is_created_exactly_once() -> None:
    with SessionLocal() as db:
        client = _client(db)
        started = start_website_onboarding(
            db, client_id=client.id, actor_user_id=None, payload=_payload()
        )
        preferences = WebsiteOnboardingCrawlPreferences(
            max_urls=2_500,
            request_delay_ms=400,
            concurrency=2,
        )
        with pytest.raises(ValueError, match="Verifieer eerst"):
            start_first_onboarding_crawl(
                db,
                started.id,
                actor_user_id=None,
                preferences=preferences,
            )

        verification = db.scalar(select(WebsiteOwnershipVerification))
        assert verification is not None
        verification.status = "verified"
        db.commit()
        first_onboarding, first_job = start_first_onboarding_crawl(
            db,
            started.id,
            actor_user_id=None,
            preferences=preferences,
        )
        repeated_onboarding, repeated_job = start_first_onboarding_crawl(
            db,
            started.id,
            actor_user_id=None,
            preferences=WebsiteOnboardingCrawlPreferences(max_urls=99_999),
        )

        assert first_job.id == repeated_job.id
        assert first_onboarding.first_crawl_job_id == first_job.id
        assert repeated_onboarding.current_step == "first_crawl"
        assert db.scalar(select(func.count()).select_from(CrawlJob)) == 1
        website = db.get(Website, started.website_id)
        assert website is not None
        assert website.settings.max_urls == 2_500
        assert website.settings.request_delay_ms == 400
        assert website.settings.concurrency == 2
        assert website.settings.respect_robots_txt is True
        assert website.settings.sitemap_urls == ["https://fresh.example.test/sitemap.xml"]


def test_first_crawl_preferences_always_require_robots_txt() -> None:
    with pytest.raises(ValidationError, match="Robots.txt respecteren is verplicht"):
        WebsiteOnboardingCrawlPreferences(respect_robots_txt=False)


def test_first_crawl_api_is_idempotent_and_resumable(client) -> None:  # type: ignore[no-untyped-def]
    customer = client.post("/api/v1/clients", json={"name": "First crawl API client"}).json()
    started = client.post(
        f"/api/v1/website-onboarding/clients/{customer['id']}",
        json={
            "request_id": str(uuid4()),
            "website_name": "First crawl API website",
            "base_url": "https://first-crawl.example.test/",
        },
    ).json()
    with SessionLocal() as db:
        verification = db.scalar(
            select(WebsiteOwnershipVerification).where(
                WebsiteOwnershipVerification.onboarding_id == UUID(started["id"])
            )
        )
        assert verification is not None
        verification.status = "verified"
        db.commit()

    payload = {
        "max_urls": 1_500,
        "request_delay_ms": 350,
        "concurrency": 3,
        "respect_robots_txt": True,
    }
    first = client.post(
        f"/api/v1/website-onboarding/{started['id']}/first-crawl",
        json=payload,
    )
    repeated = client.post(
        f"/api/v1/website-onboarding/{started['id']}/first-crawl",
        json=payload,
    )
    resumed = client.get(f"/api/v1/website-onboarding/{started['id']}")

    assert first.status_code == 202
    assert repeated.status_code == 202
    assert repeated.json()["crawl_job_id"] == first.json()["crawl_job_id"]
    assert resumed.json()["first_crawl_job_id"] == first.json()["crawl_job_id"]
    assert resumed.json()["first_crawl_status"] == "pending"
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(CrawlJob)
                .where(CrawlJob.website_id == UUID(started["website_id"]))
            )
            == 1
        )


def test_onboarding_exposes_progress_and_advances_to_results() -> None:
    with SessionLocal() as db:
        client = _client(db)
        started = start_website_onboarding(
            db, client_id=client.id, actor_user_id=None, payload=_payload()
        )
        verification = db.scalar(select(WebsiteOwnershipVerification))
        assert verification is not None
        verification.status = "verified"
        db.commit()
        onboarding, job = start_first_onboarding_crawl(
            db,
            started.id,
            actor_user_id=None,
            preferences=WebsiteOnboardingCrawlPreferences(),
        )
        run = CrawlRun(
            crawl_job_id=job.id,
            website_id=job.website_id,
            crawl_type=job.job_type,
            status="succeeded",
            phase="finalizing",
            phase_current=12,
            phase_total=12,
            discovered_urls=15,
            crawled_urls=12,
            failed_urls=1,
        )
        job.status = "partially_succeeded"
        db.add(run)
        db.commit()

        resumed = get_website_onboarding(db, onboarding.id)

        assert resumed.status == "completed"
        assert resumed.current_step == "results"
        assert resumed.first_crawl_status == "partially_succeeded"
        assert resumed.first_crawl_phase == "finalizing"
        assert resumed.first_crawl_discovered_urls == 15
        assert resumed.first_crawl_crawled_urls == 12
        assert resumed.first_crawl_failed_urls == 1
        assert resumed.analytics_quality_status == "not_configured"
        assert resumed.conversion_insights_reliable is False


def test_failed_first_crawl_retries_with_same_job_id() -> None:
    with SessionLocal() as db:
        client = _client(db)
        started = start_website_onboarding(
            db, client_id=client.id, actor_user_id=None, payload=_payload()
        )
        verification = db.scalar(select(WebsiteOwnershipVerification))
        assert verification is not None
        verification.status = "verified"
        db.commit()
        onboarding, job = start_first_onboarding_crawl(
            db,
            started.id,
            actor_user_id=None,
            preferences=WebsiteOnboardingCrawlPreferences(),
        )
        job.status = "failed"
        job.error_message = "Tijdelijke crawlerfout"
        db.commit()
        failed = get_website_onboarding(db, onboarding.id)

        retried_onboarding, retried_job = retry_first_onboarding_crawl(db, onboarding.id)

        assert failed.status == "failed"
        assert failed.first_crawl_error == "Tijdelijke crawlerfout"
        assert retried_job.id == job.id
        assert retried_job.status == "pending"
        assert retried_onboarding.status == "crawl_queued"
        assert db.scalar(select(func.count()).select_from(CrawlJob)) == 1


def test_onboarding_only_marks_conversion_insights_reliable_after_quality_check(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    with SessionLocal() as db:
        client = _client(db)
        started = start_website_onboarding(
            db, client_id=client.id, actor_user_id=None, payload=_payload()
        )
        monkeypatch.setattr(
            "app.services.website_onboarding.analytics_quality_status",
            lambda _db, _website_id: {
                "status": "reliable",
                "source": "matomo",
                "source_label": "Matomo",
                "last_checked_at": datetime.now(UTC),
            },
        )

        resumed = get_website_onboarding(db, started.id)

        assert resumed.analytics_quality_status == "reliable"
        assert resumed.analytics_quality_source == "matomo"
        assert resumed.analytics_quality_source_label == "Matomo"
        assert resumed.analytics_quality_last_checked_at is not None
        assert resumed.conversion_insights_reliable is True

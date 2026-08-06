from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.content_analysis import UrlContentOverride
from app.models.discovery import Url
from app.models.user import ClientMembership, SecurityAuditEvent, User
from app.services.content_classification import normalize_branded_terms, validate_probabilities


def test_probability_validation_and_brand_normalization() -> None:
    assert validate_probabilities({"informational": 0.7, "transactional": 0.3}) == {
        "informational": 0.7,
        "transactional": 0.3,
    }
    assert normalize_branded_terms([" Example ", "example", "SEO   Monitor"]) == [
        "example",
        "seo monitor",
    ]
    with pytest.raises(ValueError, match="add up to one"):
        validate_probabilities({"informational": 0.7})
    with pytest.raises(ValueError, match="between zero and one"):
        validate_probabilities({"informational": 1.1, "uncertain": -0.1})


def test_settings_override_and_audit_are_tenant_bound(client: TestClient) -> None:
    allowed_client = client.post("/api/v1/clients", json={"name": "Allowed"}).json()
    hidden_client = client.post("/api/v1/clients", json={"name": "Hidden"}).json()
    allowed_site = client.post(
        "/api/v1/websites",
        json={
            "client_id": allowed_client["id"],
            "name": "Allowed site",
            "base_url": "https://allowed.example.com",
        },
    ).json()
    hidden_site = client.post(
        "/api/v1/websites",
        json={
            "client_id": hidden_client["id"],
            "name": "Hidden site",
            "base_url": "https://hidden.example.com",
        },
    ).json()
    with SessionLocal() as db:
        user = User(
            email="content-admin@example.com",
            role="user",
            password_hash=hash_password("content-admin-password"),
        )
        db.add(user)
        db.flush()
        db.add(
            ClientMembership(user_id=user.id, client_id=UUID(allowed_client["id"]), role="admin")
        )
        url = Url(
            website_id=UUID(allowed_site["id"]),
            normalized_url="https://allowed.example.com/page",
        )
        db.add(url)
        db.commit()
        url_id = url.id

    from app.main import app

    browser = TestClient(app)
    assert (
        browser.post(
            "/ui/login",
            json={"email": "content-admin@example.com", "password": "content-admin-password"},
        ).status_code
        == 204
    )
    settings = browser.put(
        f"/api/v1/websites/{allowed_site['id']}/content-analysis/settings",
        json={"branded_terms": [" Example ", "example"], "sector_template": "services"},
    )
    assert settings.status_code == 200
    assert settings.json()["branded_terms"] == ["example"]
    assert (
        browser.get(f"/api/v1/websites/{hidden_site['id']}/content-analysis/settings").status_code
        == 403
    )

    override = browser.put(
        f"/api/v1/websites/{allowed_site['id']}/content-analysis/urls/{url_id}/override",
        json={"search_intent": "transactional", "is_locked": True, "rationale": "Manual review"},
    )
    assert override.status_code == 200
    assert override.json()["is_locked"] is True
    with SessionLocal() as db:
        stored = db.scalar(select(UrlContentOverride).where(UrlContentOverride.url_id == url_id))
        assert stored is not None and stored.search_intent == "transactional"
        event = db.scalar(
            select(SecurityAuditEvent).where(
                SecurityAuditEvent.event_type == "content_override_changed"
            )
        )
        assert event is not None and event.client_id == UUID(allowed_client["id"])

    assert (
        browser.delete(
            f"/api/v1/websites/{allowed_site['id']}/content-analysis/urls/{url_id}/override"
        ).status_code
        == 204
    )


def test_override_rejects_empty_or_invalid_values(client: TestClient) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Validation"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Validation site",
            "base_url": "https://validation.example.com",
        },
    ).json()
    with SessionLocal() as db:
        url = Url(
            website_id=UUID(website["id"]), normalized_url="https://validation.example.com/page"
        )
        db.add(url)
        db.commit()
        url_id = url.id
    endpoint = f"/api/v1/websites/{website['id']}/content-analysis/urls/{url_id}/override"
    assert client.put(endpoint, json={}).status_code == 422
    assert client.put(endpoint, json={"search_intent": "unknown"}).status_code == 422

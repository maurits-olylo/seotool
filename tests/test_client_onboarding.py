import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select

from app.api.routes.clients import onboard_client
from app.core.security import Principal
from app.db.session import SessionLocal
from app.models.client import Client
from app.models.discovery import CrawlJob
from app.models.website import Website, WebsiteSettings
from app.schemas.client import ClientOnboardingCreate


def test_onboarding_creates_client_website_and_settings_atomically() -> None:
    principal = Principal(user_id=None, role="superuser", is_api_key=True)
    payload = ClientOnboardingCreate(
        name="New customer",
        internal_reference="new-customer",
        website_name="Main website",
        base_url="https://www.example.com/",
        settings={
            "sitemap_urls": ["https://www.example.com/sitemap.xml"],
            "max_urls": 750,
            "request_delay_ms": 350,
            "respect_robots_txt": True,
        },
    )
    with SessionLocal() as db:
        result = onboard_client(payload, db, principal)
        assert result["client"].name == "New customer"
        assert result["website"].base_url == "https://www.example.com/"
        assert result["website"].settings is not None
        assert result["crawl_job"].job_type == "full_site_crawl"
        assert result["crawl_job"].status == "pending"
        assert result["crawl_job"].settings_snapshot["max_urls"] == 750
        assert db.scalar(select(func.count()).select_from(Client)) == 1
        assert db.scalar(select(func.count()).select_from(Website)) == 1
        assert db.scalar(select(func.count()).select_from(WebsiteSettings)) == 1
        assert db.scalar(select(func.count()).select_from(CrawlJob)) == 1
        assert result["website"].settings.sitemap_urls == ["https://www.example.com/sitemap.xml"]
        assert result["website"].settings.request_delay_ms == 350


def test_onboarding_rejects_duplicate_client_name() -> None:
    principal = Principal(user_id=None, role="superuser", is_api_key=True)
    payload = ClientOnboardingCreate(
        name="Duplicate",
        website_name="Main website",
        base_url="https://www.example.com/",
    )
    with SessionLocal() as db:
        onboard_client(payload, db, principal)
        with pytest.raises(HTTPException) as exc_info:
            onboard_client(payload, db, principal)
        assert exc_info.value.status_code == 409


def test_onboarding_normalizes_names_references_and_duplicate_whitespace() -> None:
    principal = Principal(user_id=None, role="superuser", is_api_key=True)
    first = ClientOnboardingCreate(
        name="  Acme  ",
        internal_reference="  acme-1  ",
        website_name="  Corporate site  ",
        base_url="https://www.example.com/",
    )
    duplicate = ClientOnboardingCreate(
        name="Acme ",
        internal_reference="   ",
        website_name="Another site",
        base_url="https://example.org/",
    )
    assert first.name == "Acme"
    assert first.internal_reference == "acme-1"
    assert first.website_name == "Corporate site"
    assert duplicate.internal_reference is None

    with SessionLocal() as db:
        onboard_client(first, db, principal)
        with pytest.raises(HTTPException) as exc_info:
            onboard_client(duplicate, db, principal)
        assert exc_info.value.status_code == 409


def test_client_update_rejects_null_or_whitespace_name() -> None:
    from app.schemas.client import ClientUpdate

    for invalid_name in (None, "   "):
        with pytest.raises(ValidationError):
            ClientUpdate(name=invalid_name)

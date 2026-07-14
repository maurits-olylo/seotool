import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.api.routes.clients import onboard_client
from app.core.security import Principal
from app.db.session import SessionLocal
from app.models.client import Client
from app.models.website import Website
from app.schemas.client import ClientOnboardingCreate


def test_onboarding_creates_client_website_and_settings_atomically() -> None:
    principal = Principal(user_id=None, role="superuser", is_api_key=True)
    payload = ClientOnboardingCreate(
        name="New customer",
        internal_reference="new-customer",
        website_name="Main website",
        base_url="https://www.example.com/",
    )
    with SessionLocal() as db:
        result = onboard_client(payload, db, principal)
        assert result["client"].name == "New customer"
        assert result["website"].base_url == "https://www.example.com/"
        assert result["website"].settings is not None
        assert db.scalar(select(func.count()).select_from(Client)) == 1
        assert db.scalar(select(func.count()).select_from(Website)) == 1


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

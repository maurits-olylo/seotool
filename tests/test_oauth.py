from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.integrations import IntegrationConnection
from app.services.oauth import (
    create_oauth_state,
    decrypt_token,
    encrypt_token,
    parse_oauth_state,
)


def test_google_authorize_uses_signed_state_and_read_only_scopes(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-client-secret")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "https://seo.example.com/api/v1/integrations/google/callback",
    )
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "01" * 32)
    get_settings.cache_clear()
    try:
        customer = client.post("/api/v1/clients", json={"name": "OAuth client"}).json()
        response = client.get(
            f"/api/v1/integrations/google/authorize?client_id={customer['id']}",
            follow_redirects=False,
        )
        assert response.status_code == 302
        query = parse_qs(urlparse(response.headers["location"]).query)
        assert "https://www.googleapis.com/auth/webmasters.readonly" in query["scope"][0]
        assert "https://www.googleapis.com/auth/analytics.readonly" in query["scope"][0]
        assert str(parse_oauth_state(query["state"][0])) == customer["id"]

        encrypted = encrypt_token("refresh-secret")
        assert encrypted and "refresh-secret" not in encrypted
        assert decrypt_token(encrypted) == "refresh-secret"
    finally:
        get_settings.cache_clear()


def test_google_callback_stores_encrypted_tokens(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-client-secret")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "https://seo.example.com/api/v1/integrations/google/callback",
    )
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "02" * 32)
    get_settings.cache_clear()

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.status_code = 200
            self._payload = payload

        def json(self) -> dict[str, object]:
            return self._payload

    class FakeGoogleClient:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *args):  # type: ignore[no-untyped-def]
            return None

        async def post(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return FakeResponse(
                {
                    "access_token": "plain-access",
                    "refresh_token": "plain-refresh",
                    "expires_in": 3600,
                    "scope": "openid",
                }
            )

        async def get(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return FakeResponse({"email": "owner@example.com"})

    monkeypatch.setattr(
        "app.api.routes.integrations.httpx.AsyncClient",
        lambda **kwargs: FakeGoogleClient(),
    )
    try:
        customer = client.post("/api/v1/clients", json={"name": "Callback client"}).json()
        state = create_oauth_state(UUID(customer["id"]))
        response = client.get(
            f"/api/v1/integrations/google/callback?code=auth-code&state={state}",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/?integration=google-connected"
        with SessionLocal() as db:
            connection = db.scalar(select(IntegrationConnection))
            assert connection and connection.status == "connected"
            assert connection.account_email == "owner@example.com"
            assert connection.encrypted_refresh_token != "plain-refresh"
            assert decrypt_token(connection.encrypted_refresh_token) == "plain-refresh"
    finally:
        get_settings.cache_clear()


def test_google_properties_are_loaded_for_connected_client(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "03" * 32)
    get_settings.cache_clear()

    class FakeResponse:
        status_code = 200

        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def json(self) -> dict[str, object]:
            return self._payload

    class FakeGoogleClient:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *args):  # type: ignore[no-untyped-def]
            return None

        async def get(self, url, **kwargs):  # type: ignore[no-untyped-def]
            if "webmasters" in url:
                return FakeResponse(
                    {
                        "siteEntry": [
                            {
                                "siteUrl": "sc-domain:example.com",
                                "permissionLevel": "siteOwner",
                            }
                        ]
                    }
                )
            return FakeResponse(
                {
                    "accountSummaries": [
                        {
                            "displayName": "Agency",
                            "propertySummaries": [
                                {"property": "properties/123", "displayName": "Example GA4"}
                            ],
                        }
                    ]
                }
            )

    monkeypatch.setattr(
        "app.services.google_integrations.httpx.AsyncClient",
        lambda **kwargs: FakeGoogleClient(),
    )
    try:
        customer = client.post("/api/v1/clients", json={"name": "Property client"}).json()
        with SessionLocal() as db:
            connection = IntegrationConnection(
                client_id=UUID(customer["id"]),
                provider="google",
                status="connected",
                encrypted_access_token=encrypt_token("access-token"),
                encrypted_refresh_token=encrypt_token("refresh-token"),
                token_expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            db.add(connection)
            db.commit()

        response = client.get(
            f"/api/v1/clients/{customer['id']}/integrations/google/properties"
        )
        assert response.status_code == 200
        assert response.json()["search_console"][0]["id"] == "sc-domain:example.com"
        assert response.json()["ga4"][0]["id"] == "properties/123"
    finally:
        get_settings.cache_clear()

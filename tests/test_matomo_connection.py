from uuid import UUID

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.routes import integrations
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.integrations import IntegrationConnection, WebsiteIntegration
from app.services import matomo
from app.services.oauth import decrypt_token


def test_matomo_client_uses_post_body_and_sanitizes_sites(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(matomo, "validate_public_http_url", lambda _url: None)

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert "token_auth" not in str(request.url)
        assert b"token_auth=secret-token" in request.content
        return httpx.Response(
            200,
            json=[{"idsite": 7, "name": "Human", "main_url": "https://human.nl"}],
        )

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        matomo.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    import asyncio

    sites = asyncio.run(matomo.list_matomo_sites("https://analytics.example.com", "secret-token"))
    assert sites == [{"id": "7", "name": "Human", "main_url": "https://human.nl"}]


def test_connect_and_select_human_matomo_site(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "0a" * 32)
    get_settings.cache_clear()

    async def fake_sites(_server_url: str, token: str):  # type: ignore[no-untyped-def]
        assert token == "matomo-secret"
        return [{"id": "7", "name": "Human", "main_url": "https://human.nl"}]

    monkeypatch.setattr(
        integrations,
        "normalize_matomo_server_url",
        lambda _url: "https://analytics.example.com/index.php",
    )
    monkeypatch.setattr(integrations, "list_matomo_sites", fake_sites)
    customer = client.post("/api/v1/clients", json={"name": "Human"}).json()
    website = client.post(
        "/api/v1/websites",
        json={"client_id": customer["id"], "name": "Human", "base_url": "https://human.nl"},
    ).json()
    response = client.put(
        f"/api/v1/clients/{customer['id']}/integrations/matomo",
        json={"server_url": "https://analytics.example.com", "token_auth": "matomo-secret"},
    )
    assert response.status_code == 200
    assert response.json()["sites"][0]["id"] == "7"

    with SessionLocal() as db:
        connection = db.scalar(
            select(IntegrationConnection).where(IntegrationConnection.provider == "matomo")
        )
        assert connection is not None
        assert decrypt_token(connection.encrypted_access_token) == "matomo-secret"
        connection_id = connection.id

    mapping = client.put(
        f"/api/v1/websites/{website['id']}/integrations/matomo",
        json={
            "connection_id": str(connection_id),
            "external_property_id": "7",
            "external_property_name": "Human",
        },
    )
    assert mapping.status_code == 200
    assert mapping.json()["external_property_id"] == "7"
    with SessionLocal() as db:
        selected = db.scalar(
            select(WebsiteIntegration).where(
                WebsiteIntegration.website_id == UUID(website["id"]),
                WebsiteIntegration.service == "matomo",
            )
        )
        assert selected is not None
        assert selected.external_property_id == "7"
    get_settings.cache_clear()

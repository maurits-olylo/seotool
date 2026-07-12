from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.integrations import IntegrationConnection
from app.services.oauth import decrypt_token, encrypt_token

BING_TOKEN_URL = "https://www.bing.com/webmasters/oauth/token"
BING_API_ROOT = "https://www.bing.com/webmaster/api.svc/json"


async def get_bing_access_token(db: Session, connection: IntegrationConnection) -> str:
    now = datetime.now(UTC)
    expires_at = connection.token_expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if connection.encrypted_access_token and expires_at and expires_at > now + timedelta(minutes=2):
        token = decrypt_token(connection.encrypted_access_token)
        if token:
            return token

    refresh_token = decrypt_token(connection.encrypted_refresh_token)
    if not refresh_token:
        raise ValueError("Bing connection has no refresh token")
    settings = get_settings()
    async with httpx.AsyncClient(timeout=20) as http:
        response = await http.post(
            BING_TOKEN_URL,
            data={
                "client_id": settings.bing_client_id,
                "client_secret": settings.bing_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
    if response.status_code != 200:
        connection.status = "error"
        connection.last_error = "Bing access token could not be refreshed"
        db.commit()
        raise ValueError(connection.last_error)
    payload = response.json()
    access_token = payload["access_token"]
    connection.encrypted_access_token = encrypt_token(access_token)
    if payload.get("refresh_token"):
        connection.encrypted_refresh_token = encrypt_token(payload["refresh_token"])
    connection.token_expires_at = now + timedelta(seconds=int(payload.get("expires_in", 3600)))
    connection.status = "connected"
    connection.last_error = None
    db.commit()
    return access_token


async def list_bing_sites(
    db: Session, connection: IntegrationConnection
) -> list[dict[str, str | bool]]:
    access_token = await get_bing_access_token(db, connection)
    async with httpx.AsyncClient(timeout=30) as http:
        response = await http.get(
            f"{BING_API_ROOT}/GetUserSites",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if response.status_code != 200:
        raise ValueError("Bing Webmaster sites could not be loaded")
    payload = response.json().get("d", [])
    sites = payload if isinstance(payload, list) else payload.get("Results", [])
    return sorted(
        [
            {
                "id": item["Url"],
                "name": item["Url"],
                "verified": bool(item.get("IsVerified")),
            }
            for item in sites
            if item.get("Url") and item.get("IsVerified")
        ],
        key=lambda item: str(item["name"]),
    )

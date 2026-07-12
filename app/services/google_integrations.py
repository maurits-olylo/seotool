from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.integrations import IntegrationConnection
from app.services.oauth import decrypt_token, encrypt_token


async def get_google_access_token(db: Session, connection: IntegrationConnection) -> str:
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
        raise ValueError("Google connection has no refresh token")
    settings = get_settings()
    async with httpx.AsyncClient(timeout=20) as http:
        response = await http.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
    if response.status_code != 200:
        connection.status = "error"
        connection.last_error = "Google access token could not be refreshed"
        db.commit()
        raise ValueError(connection.last_error)
    payload = response.json()
    access_token = payload["access_token"]
    connection.encrypted_access_token = encrypt_token(access_token)
    connection.token_expires_at = now + timedelta(seconds=int(payload.get("expires_in", 3600)))
    connection.status = "connected"
    connection.last_error = None
    db.commit()
    return access_token


async def list_google_properties(
    db: Session, connection: IntegrationConnection
) -> dict[str, list[dict[str, str]]]:
    access_token = await get_google_access_token(db, connection)
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=30) as http:
        search_console_response = await http.get(
            "https://www.googleapis.com/webmasters/v3/sites", headers=headers
        )
        analytics_response = await http.get(
            "https://analyticsadmin.googleapis.com/v1beta/accountSummaries",
            headers=headers,
            params={"pageSize": 200},
        )
    if search_console_response.status_code != 200:
        raise ValueError("Search Console properties could not be loaded")
    if analytics_response.status_code != 200:
        raise ValueError("GA4 properties could not be loaded")

    search_console = [
        {
            "id": item["siteUrl"],
            "name": item["siteUrl"],
            "permission": item.get("permissionLevel", ""),
        }
        for item in search_console_response.json().get("siteEntry", [])
        if item.get("permissionLevel") != "siteUnverifiedUser"
    ]
    ga4: list[dict[str, str]] = []
    for account in analytics_response.json().get("accountSummaries", []):
        for item in account.get("propertySummaries", []):
            ga4.append(
                {
                    "id": item["property"],
                    "name": item.get("displayName", item["property"]),
                    "account": account.get("displayName", ""),
                }
            )
    return {
        "search_console": sorted(search_console, key=lambda item: item["name"]),
        "ga4": sorted(ga4, key=lambda item: item["name"]),
    }

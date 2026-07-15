import re
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.discovery import Url
from app.models.integrations import (
    BingPageMetric,
    BingQueryMetric,
    IntegrationConnection,
    WebsiteIntegration,
)
from app.services.oauth import decrypt_token, encrypt_token
from app.services.url_normalization import InvalidUrlError, normalize_url

BING_TOKEN_URL = "https://www.bing.com/webmasters/oauth/token"
BING_API_ROOT = "https://www.bing.com/webmaster/api.svc/json"
BING_DATE_RE = re.compile(r"/Date\((\d+)(?:[+-]\d+)?\)/")


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


async def sync_bing_webmaster(
    db: Session, website_id: UUID, days: int | None = None
) -> dict[str, object]:
    mapping = db.scalar(
        select(WebsiteIntegration).where(
            WebsiteIntegration.website_id == website_id,
            WebsiteIntegration.service == "bing_webmaster",
            WebsiteIntegration.status.in_(["active", "error"]),
        )
    )
    if not mapping:
        raise ValueError("Bing Webmaster site is not mapped")
    connection = db.get(IntegrationConnection, mapping.connection_id)
    if not connection or connection.status != "connected":
        raise ValueError("Bing account is not connected")
    token = await get_bing_access_token(db, connection)

    try:
        async with httpx.AsyncClient(timeout=60) as http:
            page_rows = await _bing_rows(
                http, "GetPageStats", mapping.external_property_id, token
            )
            query_rows = await _bing_rows(
                http, "GetQueryStats", mapping.external_property_id, token
            )
    except (httpx.HTTPError, ValueError) as exc:
        mapping.status = "error"
        mapping.settings = {**mapping.settings, "last_error": str(exc)}
        db.commit()
        raise ValueError("Bing Webmaster data could not be loaded") from exc

    end_date = date.today()
    start_date = end_date - timedelta(days=(days or 480) - 1)
    url_map = {
        item.normalized_url: item.id
        for item in db.scalars(select(Url).where(Url.website_id == website_id))
    }
    db.execute(
        delete(BingPageMetric).where(
            BingPageMetric.website_id == website_id,
            BingPageMetric.date >= start_date,
        )
    )
    db.execute(
        delete(BingQueryMetric).where(
            BingQueryMetric.website_id == website_id,
            BingQueryMetric.date >= start_date,
        )
    )
    pages: list[BingPageMetric] = []
    matched = 0
    for row in page_rows:
        metric_date = _bing_date(row.get("Date"))
        page_url = str(row.get("Query") or "").strip()
        if not metric_date or metric_date < start_date or not page_url:
            continue
        try:
            url_id = url_map.get(normalize_url(page_url))
        except InvalidUrlError:
            url_id = None
        matched += int(url_id is not None)
        pages.append(_page_metric(website_id, url_id, metric_date, page_url, row))
    queries = [
        _query_metric(website_id, metric_date, str(row.get("Query") or "").strip(), row)
        for row in query_rows
        if (metric_date := _bing_date(row.get("Date")))
        and metric_date >= start_date
        and str(row.get("Query") or "").strip()
    ]
    db.add_all([*pages, *queries])
    now = datetime.now(UTC)
    mapping.status = "active"
    mapping.last_synced_at = now
    mapping.settings = {
        **mapping.settings,
        "last_import_start": start_date.isoformat(),
        "last_import_end": end_date.isoformat(),
        "last_page_rows": len(pages),
        "last_page_matched": matched,
        "last_query_rows": len(queries),
        "last_error": None,
    }
    connection.last_synced_at = now
    db.commit()
    return {
        "status": "succeeded",
        "start_date": start_date,
        "end_date": end_date,
        "page_rows": len(pages),
        "matched_urls": matched,
        "unmatched_urls": len(pages) - matched,
        "query_rows": len(queries),
    }


async def _bing_rows(
    http: httpx.AsyncClient, method: str, site_url: str, token: str
) -> list[dict[str, object]]:
    response = await http.get(
        f"{BING_API_ROOT}/{method}",
        params={"siteUrl": site_url},
        headers={"Authorization": f"Bearer {token}"},
    )
    if response.status_code != 200:
        raise ValueError(f"Bing Webmaster {method} data could not be loaded")
    payload = response.json().get("d", [])
    return payload if isinstance(payload, list) else payload.get("Results", [])


def _bing_date(value: object) -> date | None:
    match = BING_DATE_RE.fullmatch(str(value or ""))
    if not match:
        return None
    return datetime.fromtimestamp(int(match.group(1)) / 1000, tz=UTC).date()


def _page_metric(
    website_id: UUID, url_id: UUID | None, metric_date: date, page_url: str, row: dict[str, object]
) -> BingPageMetric:
    return BingPageMetric(
        website_id=website_id,
        url_id=url_id,
        date=metric_date,
        page_url=page_url,
        clicks=int(row.get("Clicks") or 0),
        impressions=int(row.get("Impressions") or 0),
        average_click_position=float(row.get("AvgClickPosition") or 0),
        average_impression_position=float(row.get("AvgImpressionPosition") or 0),
    )


def _query_metric(
    website_id: UUID, metric_date: date, query: str, row: dict[str, object]
) -> BingQueryMetric:
    return BingQueryMetric(
        website_id=website_id,
        date=metric_date,
        query=query,
        clicks=int(row.get("Clicks") or 0),
        impressions=int(row.get("Impressions") or 0),
        average_click_position=float(row.get("AvgClickPosition") or 0),
        average_impression_position=float(row.get("AvgImpressionPosition") or 0),
    )

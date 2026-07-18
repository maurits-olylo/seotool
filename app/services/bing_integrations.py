import re
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from uuid import UUID

import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.discovery import Url
from app.models.integrations import (
    BingInboundLink,
    BingLinkTarget,
    BingPageMetric,
    BingQueryMetric,
    IntegrationConnection,
    WebsiteIntegration,
)
from app.models.website import Website
from app.services.oauth import decrypt_token, encrypt_token
from app.services.url_matching import find_equivalent_website_url_id
from app.services.url_normalization import InvalidUrlError

BING_TOKEN_URL = "https://www.bing.com/webmasters/oauth/token"
BING_API_ROOT = "https://www.bing.com/webmaster/api.svc/json"
BING_DATE_RE = re.compile(r"/Date\((\d+)(?:[+-]\d+)?\)/")
MAX_LINK_COUNT_PAGES = 500
MAX_LINK_DETAIL_TARGETS = 500
MAX_LINK_DETAIL_PAGES = 100


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
            page_rows = await _bing_rows(http, "GetPageStats", mapping.external_property_id, token)
            query_rows = await _bing_rows(
                http, "GetQueryStats", mapping.external_property_id, token
            )
            link_counts, counts_truncated = await _bing_link_counts(
                http, mapping.external_property_id, token
            )
            link_details, covered_targets, details_truncated = await _bing_link_details(
                http, mapping.external_property_id, token, link_counts
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
    website = db.get(Website, website_id)
    if website is None:
        raise ValueError("Website does not exist")
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
            url_id = find_equivalent_website_url_id(url_map, page_url, base_url=website.base_url)
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
    link_result = _store_bing_links(
        db,
        website_id,
        url_map,
        link_counts,
        link_details,
        covered_targets,
        base_url=website.base_url,
        counts_complete=bool(link_counts) and not counts_truncated,
        observed_at=now,
    )
    mapping.status = "active"
    mapping.last_synced_at = now
    mapping.settings = {
        **mapping.settings,
        "last_import_start": start_date.isoformat(),
        "last_import_end": end_date.isoformat(),
        "last_page_rows": len(pages),
        "last_page_matched": matched,
        "last_query_rows": len(queries),
        "last_link_targets": link_result["link_targets"],
        "last_link_details": link_result["link_details"],
        "link_counts_truncated": counts_truncated,
        "link_details_truncated": details_truncated,
        "link_api_status": "available" if link_counts else "unavailable_empty",
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
        **link_result,
        "link_counts_truncated": counts_truncated,
        "link_details_truncated": details_truncated,
        "link_api_status": "available" if link_counts else "unavailable_empty",
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


async def _bing_link_counts(
    http: httpx.AsyncClient, site_url: str, token: str
) -> tuple[list[dict[str, object]], bool]:
    rows: list[dict[str, object]] = []
    page = 0
    total_pages = 1
    while page < min(total_pages, MAX_LINK_COUNT_PAGES):
        payload = await _bing_object(http, "GetLinkCounts", site_url, token, page=page)
        batch = payload.get("Links", [])
        if isinstance(batch, list):
            rows.extend(item for item in batch if isinstance(item, dict))
        total_pages = max(1, int(payload.get("TotalPages") or 1))
        page += 1
    return rows, total_pages > MAX_LINK_COUNT_PAGES


async def _bing_link_details(
    http: httpx.AsyncClient,
    site_url: str,
    token: str,
    counts: list[dict[str, object]],
) -> tuple[list[dict[str, object]], set[str], bool]:
    targets = sorted(counts, key=lambda item: int(item.get("Count") or 0), reverse=True)
    selected = targets[:MAX_LINK_DETAIL_TARGETS]
    details: list[dict[str, object]] = []
    covered_targets: set[str] = set()
    truncated = len(targets) > len(selected)
    for target in selected:
        target_url = str(target.get("Url") or "").strip()
        if not target_url:
            continue
        page = 0
        total_pages = 1
        while page < min(total_pages, MAX_LINK_DETAIL_PAGES):
            payload = await _bing_object(
                http, "GetUrlLinks", site_url, token, page=page, link=target_url
            )
            batch = payload.get("Details", [])
            if isinstance(batch, list):
                details.extend(
                    {**item, "TargetUrl": target_url} for item in batch if isinstance(item, dict)
                )
            total_pages = max(1, int(payload.get("TotalPages") or 1))
            if total_pages > MAX_LINK_DETAIL_PAGES:
                truncated = True
            page += 1
        if total_pages <= MAX_LINK_DETAIL_PAGES:
            covered_targets.add(target_url)
    return details, covered_targets, truncated


async def _bing_object(
    http: httpx.AsyncClient,
    method: str,
    site_url: str,
    token: str,
    **params: object,
) -> dict[str, object]:
    response = await http.get(
        f"{BING_API_ROOT}/{method}",
        params={"siteUrl": site_url, **params},
        headers={"Authorization": f"Bearer {token}"},
    )
    if response.status_code != 200:
        raise ValueError(f"Bing Webmaster {method} data could not be loaded")
    payload = response.json().get("d", {})
    return payload if isinstance(payload, dict) else {}


def _store_bing_links(
    db: Session,
    website_id: UUID,
    url_map: dict[str, UUID],
    counts: list[dict[str, object]],
    details: list[dict[str, object]],
    covered_targets: set[str],
    *,
    base_url: str,
    counts_complete: bool,
    observed_at: datetime,
) -> dict[str, int]:
    if counts_complete:
        db.execute(
            update(BingLinkTarget)
            .where(BingLinkTarget.website_id == website_id)
            .values(is_active=False)
        )
    if covered_targets:
        db.execute(
            update(BingInboundLink)
            .where(
                BingInboundLink.website_id == website_id,
                BingInboundLink.target_url.in_(covered_targets),
            )
            .values(is_active=False)
        )
    for item in counts:
        target_url = str(item.get("Url") or "").strip()
        if not target_url:
            continue
        record = db.scalar(
            select(BingLinkTarget).where(
                BingLinkTarget.website_id == website_id,
                BingLinkTarget.target_url == target_url,
            )
        )
        if record is None:
            record = BingLinkTarget(
                website_id=website_id,
                target_url=target_url,
                first_seen_at=observed_at,
                last_seen_at=observed_at,
            )
            db.add(record)
        try:
            record.url_id = find_equivalent_website_url_id(url_map, target_url, base_url=base_url)
        except InvalidUrlError:
            record.url_id = None
        record.inbound_link_count = int(item.get("Count") or 0)
        record.last_seen_at = observed_at
        record.is_active = True
    for item in details:
        target_url = str(item.get("TargetUrl") or "").strip()
        source_url = str(item.get("Url") or "").strip()
        anchor_text = str(item.get("AnchorText") or "").strip()
        if not target_url or not source_url:
            continue
        link_key = sha256(f"{target_url}\n{source_url}\n{anchor_text}".encode()).hexdigest()
        record = db.scalar(
            select(BingInboundLink).where(
                BingInboundLink.website_id == website_id,
                BingInboundLink.link_key == link_key,
            )
        )
        if record is None:
            record = BingInboundLink(
                website_id=website_id,
                link_key=link_key,
                target_url=target_url,
                source_url=source_url,
                anchor_text=anchor_text,
                first_seen_at=observed_at,
                last_seen_at=observed_at,
            )
            db.add(record)
        record.last_seen_at = observed_at
        record.is_active = True
    return {"link_targets": len(counts), "link_details": len(details)}


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

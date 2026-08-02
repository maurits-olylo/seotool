from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.discovery import Url
from app.models.integrations import (
    IntegrationConnection,
    UrlInspectionResult,
    WebsiteIntegration,
)
from app.models.issues import Change, Issue
from app.services.google_integrations import get_google_access_token
from app.services.url_inspection_analysis import analyze_url_inspection_result

URL_INSPECTION_ENDPOINT = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
DEFAULT_INSPECTION_LIMIT = 25
MAX_INSPECTION_LIMIT = 200
MINIMUM_REINSPECTION_DAYS = 7
ACTIVE_ISSUE_STATUSES = {
    "new",
    "review",
    "accepted",
    "planned",
    "in_progress",
    "waiting_for_client",
}


async def sync_url_inspection(
    db: Session,
    website_id: UUID,
    *,
    limit: int = DEFAULT_INSPECTION_LIMIT,
) -> dict[str, object]:
    if not 1 <= limit <= MAX_INSPECTION_LIMIT:
        raise ValueError(f"URL Inspection limit must be between 1 and {MAX_INSPECTION_LIMIT}")
    mapping = db.scalar(
        select(WebsiteIntegration).where(
            WebsiteIntegration.website_id == website_id,
            WebsiteIntegration.service == "search_console",
            WebsiteIntegration.status.in_(["active", "error"]),
        )
    )
    if mapping is None:
        raise ValueError("Search Console property is not mapped")
    connection = db.get(IntegrationConnection, mapping.connection_id)
    if connection is None or connection.status != "connected":
        raise ValueError("Google account is not connected")
    candidates = select_inspection_urls(db, website_id=website_id, limit=limit)
    if not candidates:
        return {"status": "succeeded", "selected": 0, "inspected": 0, "failed": 0}

    token = await get_google_access_token(db, connection)
    inspected = 0
    failures: list[dict[str, str]] = []
    async with httpx.AsyncClient(timeout=30) as http:
        for url in candidates:
            response = await http.post(
                URL_INSPECTION_ENDPOINT,
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "inspectionUrl": url.normalized_url,
                    "siteUrl": mapping.external_property_id,
                    "languageCode": "en-US",
                },
            )
            if response.status_code != 200:
                failures.append(
                    {"url": url.normalized_url, "status_code": str(response.status_code)}
                )
                continue
            result = inspection_result_from_response(
                website_id=website_id,
                url_id=url.id,
                payload=response.json(),
            )
            db.add(result)
            db.flush()
            analyze_url_inspection_result(db, result)
            inspected += 1
    mapping.settings = {
        **mapping.settings,
        "url_inspection_last_sync": datetime.now(UTC).isoformat(),
        "url_inspection_selected": len(candidates),
        "url_inspection_succeeded": inspected,
        "url_inspection_failed": len(failures),
    }
    db.commit()
    return {
        "status": "partially_succeeded" if failures else "succeeded",
        "selected": len(candidates),
        "inspected": inspected,
        "failed": len(failures),
        "failures": failures,
    }


def select_inspection_urls(db: Session, *, website_id: UUID, limit: int) -> list[Url]:
    urls = list(
        db.scalars(
            select(Url).where(
                Url.website_id == website_id,
                Url.is_active.is_(True),
                Url.current_status_code == 200,
                Url.is_indexable.is_not(False),
            )
        )
    )
    latest: dict[UUID, datetime] = {}
    for url_id, inspected_at in db.execute(
        select(UrlInspectionResult.url_id, UrlInspectionResult.inspected_at)
        .where(UrlInspectionResult.website_id == website_id)
        .order_by(UrlInspectionResult.inspected_at.desc())
    ):
        latest.setdefault(url_id, inspected_at)
    issue_url_ids = set(
        db.scalars(
            select(Issue.url_id).where(
                Issue.website_id == website_id,
                Issue.url_id.is_not(None),
                Issue.status.in_(ACTIVE_ISSUE_STATUSES),
                Issue.category == "indexation",
            )
        )
    )
    changed_url_ids = set(
        db.scalars(
            select(Change.url_id).where(
                Change.website_id == website_id,
                Change.detected_at >= datetime.now(UTC) - timedelta(days=28),
            )
        )
    )
    stale_before = datetime.now(UTC) - timedelta(days=MINIMUM_REINSPECTION_DAYS)
    eligible = [
        url
        for url in urls
        if url.id not in latest or _as_utc(latest[url.id]) <= stale_before
    ]
    eligible.sort(
        key=lambda url: (
            0 if url.is_important else 1,
            0 if url.id in issue_url_ids else 1,
            0 if url.id in changed_url_ids else 1,
            _as_utc(latest[url.id]) if url.id in latest else datetime.min.replace(tzinfo=UTC),
            url.normalized_url,
        )
    )
    return eligible[:limit]


def inspection_result_from_response(
    *, website_id: UUID, url_id: UUID, payload: dict[str, object]
) -> UrlInspectionResult:
    result = payload.get("inspectionResult")
    result = result if isinstance(result, dict) else {}
    index = result.get("indexStatusResult")
    index = index if isinstance(index, dict) else {}
    rich_results = result.get("richResultsResult")
    return UrlInspectionResult(
        website_id=website_id,
        url_id=url_id,
        inspected_at=datetime.now(UTC),
        inspection_result_link=_string(result.get("inspectionResultLink")),
        verdict=_string(index.get("verdict")),
        coverage_state=_string(index.get("coverageState")),
        indexing_state=_string(index.get("indexingState")),
        page_fetch_state=_string(index.get("pageFetchState")),
        robots_txt_state=_string(index.get("robotsTxtState")),
        last_crawl_time=_timestamp(index.get("lastCrawlTime")),
        google_canonical=_string(index.get("googleCanonical")),
        user_canonical=_string(index.get("userCanonical")),
        referring_urls=_string_list(index.get("referringUrls")),
        sitemap_urls=_string_list(index.get("sitemap")),
        rich_results=rich_results if isinstance(rich_results, dict) else {},
        raw_response=result,
    )


def _timestamp(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


def _string(value: object) -> str | None:
    return str(value) if value is not None else None


def _string_list(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)

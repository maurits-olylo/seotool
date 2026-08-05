import asyncio
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.integrations import (
    BingPageMetric,
    GoogleAnalyticsMetric,
    SearchConsoleMetric,
    SearchConsoleQueryMetric,
    WebsiteIntegration,
)
from app.services.bing_integrations import sync_bing_webmaster
from app.services.google_analytics import sync_google_analytics
from app.services.matomo import sync_matomo
from app.services.search_console import sync_search_console
from app.services.url_inspection import sync_url_inspection

logger = structlog.get_logger()
HISTORY_CHUNK_DAYS = 28


def _date_as_iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _history_chunks(days: int, *, through: date | None = None) -> list[tuple[date, date]]:
    end_date = through or date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)
    chunks: list[tuple[date, date]] = []
    chunk_start = start_date
    while chunk_start <= end_date:
        chunk_end = min(chunk_start + timedelta(days=HISTORY_CHUNK_DAYS - 1), end_date)
        chunks.append((chunk_start, chunk_end))
        chunk_start = chunk_end + timedelta(days=1)
    return chunks


def _history_result(results: list[dict[str, object]]) -> dict[str, object]:
    return {
        "status": "succeeded",
        "chunks": len(results),
        "start_date": results[0]["start_date"],
        "end_date": results[-1]["end_date"],
    }


async def _sync_search_console_history(
    db: Session, website_id: UUID, days: int | None
) -> dict[str, object]:
    if not days or days <= HISTORY_CHUNK_DAYS:
        return await sync_search_console(db, website_id, days)
    results: list[dict[str, object]] = []
    for chunk_start, chunk_end in _history_chunks(days):
        chunk_days = (chunk_end - chunk_start).days + 1
        results.append(
            await sync_search_console(db, website_id, chunk_days, through=chunk_end)
        )
    return _history_result(results)


async def _sync_matomo_history(
    db: Session, website_id: UUID, days: int | None
) -> dict[str, object]:
    if not days or days <= HISTORY_CHUNK_DAYS:
        return await sync_matomo(db, website_id, days)
    results: list[dict[str, object]] = []
    for chunk_start, chunk_end in _history_chunks(days):
        chunk_days = (chunk_end - chunk_start).days + 1
        results.append(await sync_matomo(db, website_id, chunk_days, through=chunk_end))
    return _history_result(results)


def synchronize_website_integrations(website_id: str, days: int | None = None) -> None:
    asyncio.run(_synchronize_website_integrations(UUID(website_id), days))


async def _synchronize_website_integrations(website_id: UUID, days: int | None = None) -> None:
    with SessionLocal() as db:
        _set_history_sync_status(db, website_id, "running", days=days)
        services = set(
            db.scalars(
                select(WebsiteIntegration.service).where(
                    WebsiteIntegration.website_id == website_id,
                    WebsiteIntegration.service.in_(
                        ["search_console", "ga4", "bing_webmaster", "matomo"]
                    ),
                )
            )
        )
        errors: list[str] = []
        if "search_console" in services:
            try:
                result = await _sync_search_console_history(db, website_id, days)
                logger.info("search_console_sync_succeeded", website_id=str(website_id), **result)
                inspection = await sync_url_inspection(db, website_id)
                logger.info(
                    "url_inspection_sync_succeeded", website_id=str(website_id), **inspection
                )
            except Exception as exc:
                db.rollback()
                logger.exception("search_console_sync_failed", website_id=str(website_id))
                errors.append(f"Search Console: {exc}")
        if "ga4" in services:
            try:
                result = await sync_google_analytics(db, website_id, days)
                logger.info("ga4_sync_succeeded", website_id=str(website_id), **result)
            except Exception as exc:
                db.rollback()
                logger.exception("ga4_sync_failed", website_id=str(website_id))
                errors.append(f"GA4: {exc}")
        if "matomo" in services:
            try:
                result = await _sync_matomo_history(db, website_id, days)
                logger.info("matomo_sync_succeeded", website_id=str(website_id), **result)
            except Exception as exc:
                db.rollback()
                logger.exception("matomo_sync_failed", website_id=str(website_id))
                errors.append(f"Matomo: {exc}")
        if "bing_webmaster" in services:
            try:
                result = await sync_bing_webmaster(db, website_id, days)
                logger.info("bing_sync_succeeded", website_id=str(website_id), **result)
            except Exception as exc:
                db.rollback()
                logger.exception("bing_sync_failed", website_id=str(website_id))
                errors.append(f"Bing: {exc}")
        if errors:
            message = "; ".join(errors)
            _set_history_sync_status(db, website_id, "failed", days=days, error=message)
            raise RuntimeError(message)
        _set_history_sync_status(db, website_id, "succeeded", days=days)


def _set_history_sync_status(
    db: Session,
    website_id: UUID,
    status: str,
    *,
    days: int | None,
    error: str | None = None,
) -> None:
    """Persist queue state on all mapped data sources so it survives a browser refresh."""
    mappings = list(
        db.scalars(
            select(WebsiteIntegration).where(
                WebsiteIntegration.website_id == website_id,
                WebsiteIntegration.service.in_(
                    ["search_console", "ga4", "bing_webmaster", "matomo"]
                ),
            )
        )
    )
    now = datetime.now(UTC).isoformat()
    coverage: dict[str, str | None] = {
        "gsc_from": _date_as_iso(
            db.scalar(
                select(func.min(SearchConsoleMetric.date)).where(
                    SearchConsoleMetric.website_id == website_id
                )
            )
        ),
        "gsc_query_from": _date_as_iso(
            db.scalar(
                select(func.min(SearchConsoleQueryMetric.date)).where(
                    SearchConsoleQueryMetric.website_id == website_id
                )
            )
        ),
        "ga4_from": _date_as_iso(
            db.scalar(
                select(func.min(GoogleAnalyticsMetric.date)).where(
                    GoogleAnalyticsMetric.website_id == website_id
                )
            )
        ),
    }
    if any(mapping.service == "bing_webmaster" for mapping in mappings):
        coverage["bing_from"] = _date_as_iso(
            db.scalar(
                select(func.min(BingPageMetric.date)).where(BingPageMetric.website_id == website_id)
            )
        )
    for mapping in mappings:
        previous = dict(mapping.settings.get("history_sync", {}))
        details = {
            **previous,
            "status": status,
            "days": days,
            "queued_at": previous.get("queued_at", now),
            "updated_at": now,
            "error": error,
            **({"completed_at": now, "coverage": coverage} if status == "succeeded" else {}),
        }
        mapping.settings = {**mapping.settings, "history_sync": details}
    db.commit()

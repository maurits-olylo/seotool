import asyncio
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.integrations import GoogleAnalyticsMetric, SearchConsoleMetric, WebsiteIntegration
from app.services.google_analytics import sync_google_analytics
from app.services.search_console import sync_search_console

logger = structlog.get_logger()


def synchronize_website_integrations(website_id: str, days: int | None = None) -> None:
    asyncio.run(_synchronize_website_integrations(UUID(website_id), days))


async def _synchronize_website_integrations(website_id: UUID, days: int | None = None) -> None:
    with SessionLocal() as db:
        _set_history_sync_status(db, website_id, "running", days=days)
        services = set(
            db.scalars(
                select(WebsiteIntegration.service).where(
                    WebsiteIntegration.website_id == website_id,
                    WebsiteIntegration.service.in_(["search_console", "ga4"]),
                )
            )
        )
        errors: list[str] = []
        if "search_console" in services:
            try:
                result = await sync_search_console(db, website_id, days)
                logger.info("search_console_sync_succeeded", website_id=str(website_id), **result)
            except Exception as exc:
                logger.exception("search_console_sync_failed", website_id=str(website_id))
                errors.append(f"Search Console: {exc}")
        if "ga4" in services:
            try:
                result = await sync_google_analytics(db, website_id, days)
                logger.info("ga4_sync_succeeded", website_id=str(website_id), **result)
            except Exception as exc:
                logger.exception("ga4_sync_failed", website_id=str(website_id))
                errors.append(f"GA4: {exc}")
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
    """Persist queue state on both Google mappings so it survives a browser refresh."""
    mappings = list(
        db.scalars(
            select(WebsiteIntegration).where(
                WebsiteIntegration.website_id == website_id,
                WebsiteIntegration.service.in_(["search_console", "ga4"]),
            )
        )
    )
    now = datetime.now(UTC).isoformat()
    coverage = {
        "gsc_from": db.scalar(
            select(func.min(SearchConsoleMetric.date)).where(
                SearchConsoleMetric.website_id == website_id
            )
        ),
        "ga4_from": db.scalar(
            select(func.min(GoogleAnalyticsMetric.date)).where(
                GoogleAnalyticsMetric.website_id == website_id
            )
        ),
    }
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

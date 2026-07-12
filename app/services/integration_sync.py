import asyncio
from uuid import UUID

import structlog
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.integrations import WebsiteIntegration
from app.services.google_analytics import sync_google_analytics
from app.services.search_console import sync_search_console

logger = structlog.get_logger()


def synchronize_website_integrations(website_id: str) -> None:
    asyncio.run(_synchronize_website_integrations(UUID(website_id)))


async def _synchronize_website_integrations(website_id: UUID) -> None:
    with SessionLocal() as db:
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
                result = await sync_search_console(db, website_id)
                logger.info("search_console_sync_succeeded", website_id=str(website_id), **result)
            except Exception as exc:
                logger.exception("search_console_sync_failed", website_id=str(website_id))
                errors.append(f"Search Console: {exc}")
        if "ga4" in services:
            try:
                result = await sync_google_analytics(db, website_id)
                logger.info("ga4_sync_succeeded", website_id=str(website_id), **result)
            except Exception as exc:
                logger.exception("ga4_sync_failed", website_id=str(website_id))
                errors.append(f"GA4: {exc}")
        if errors:
            raise RuntimeError("; ".join(errors))

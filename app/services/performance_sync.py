import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.crawl import UrlSnapshot
from app.models.discovery import Url
from app.models.issues import Change, Issue
from app.models.performance import PerformanceObservation
from app.models.website import Website
from app.services.performance_analysis import (
    MAX_PERFORMANCE_CANDIDATES,
    PerformanceCandidate,
    observation_from_pagespeed_response,
    select_performance_candidates,
)
from app.services.performance_issue_analysis import analyze_performance_observation
from app.services.template_issue_analysis import analyze_template_issue_clusters

PAGESPEED_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
MINIMUM_RECHECK_DAYS = 7
ACTIVE_ISSUE_STATUSES = {
    "new",
    "review",
    "accepted",
    "planned",
    "in_progress",
    "waiting_for_client",
}
logger = structlog.get_logger()


def execute_performance_sync(website_id: str, strategy: str, limit: int) -> None:
    asyncio.run(_execute_performance_sync(UUID(website_id), strategy=strategy, limit=limit))


async def _execute_performance_sync(website_id: UUID, *, strategy: str, limit: int) -> None:
    with SessionLocal() as db:
        result = await sync_pagespeed_performance(
            db,
            website_id=website_id,
            strategy=strategy,
            limit=limit,
        )
        logger.info("performance_sync_finished", website_id=str(website_id), **result)


async def sync_pagespeed_performance(
    db: Session,
    *,
    website_id: UUID,
    strategy: str = "mobile",
    limit: int = MAX_PERFORMANCE_CANDIDATES,
    http: httpx.AsyncClient | None = None,
) -> dict[str, object]:
    settings = get_settings()
    if not settings.pagespeed_enabled or not settings.pagespeed_api_key:
        raise ValueError("PageSpeed is not enabled")
    if strategy not in {"mobile", "desktop"}:
        raise ValueError("PageSpeed strategy must be mobile or desktop")
    if not 1 <= limit <= MAX_PERFORMANCE_CANDIDATES:
        raise ValueError(f"PageSpeed limit must be between 1 and {MAX_PERFORMANCE_CANDIDATES}")

    website = db.scalar(select(Website).where(Website.id == website_id).with_for_update())
    if website is None:
        raise ValueError("Website does not exist")
    candidates = select_database_candidates(
        db,
        website_id=website_id,
        strategy=strategy,
        limit=limit,
    )
    if not candidates:
        db.commit()
        return {"status": "succeeded", "selected": 0, "measured": 0, "failed": 0}

    owned_client = http is None
    client = http or httpx.AsyncClient(timeout=60)
    measured = 0
    failures: list[dict[str, str]] = []
    try:
        for candidate in candidates:
            try:
                response = await client.get(
                    PAGESPEED_ENDPOINT,
                    params={
                        "url": candidate.url.normalized_url,
                        "strategy": strategy,
                        "key": settings.pagespeed_api_key,
                        "category": ["performance", "accessibility", "best-practices", "seo"],
                    },
                )
            except httpx.HTTPError:
                failures.append({"url": candidate.url.normalized_url, "error": "request_failed"})
                _store_failure(
                    db,
                    website_id=website_id,
                    url=candidate.url,
                    strategy=strategy,
                    error_code="request_failed",
                    error_message="PageSpeed request failed without a usable response",
                )
                continue
            if response.status_code != 200:
                code = f"http_{response.status_code}"
                failures.append({"url": candidate.url.normalized_url, "error": code})
                _store_failure(
                    db,
                    website_id=website_id,
                    url=candidate.url,
                    strategy=strategy,
                    error_code=code,
                    error_message="PageSpeed returned an unsuccessful HTTP status",
                )
                continue
            try:
                payload = response.json()
            except ValueError:
                payload = None
            if not isinstance(payload, dict):
                failures.append(
                    {"url": candidate.url.normalized_url, "error": "invalid_response"}
                )
                _store_failure(
                    db,
                    website_id=website_id,
                    url=candidate.url,
                    strategy=strategy,
                    error_code="invalid_response",
                    error_message="PageSpeed returned an unreadable response",
                )
                continue
            observation = observation_from_pagespeed_response(
                website_id=website_id,
                url_id=candidate.url.id,
                requested_url=candidate.url.normalized_url,
                strategy=strategy,
                payload=payload,
            )
            db.add(observation)
            db.flush()
            analyze_performance_observation(db, observation)
            db.commit()
            measured += 1
    finally:
        if owned_client:
            await client.aclose()
    latest_run_id = db.scalar(
        select(UrlSnapshot.crawl_run_id)
        .join(Url, Url.id == UrlSnapshot.url_id)
        .where(Url.website_id == website_id)
        .order_by(UrlSnapshot.checked_at.desc())
        .limit(1)
    )
    if measured and latest_run_id is not None:
        analyze_template_issue_clusters(
            db, website_id=website_id, crawl_run_id=latest_run_id
        )
        db.commit()
    return {
        "status": "partially_succeeded" if failures else "succeeded",
        "selected": len(candidates),
        "measured": measured,
        "failed": len(failures),
        "failures": failures,
    }


def select_database_candidates(
    db: Session,
    *,
    website_id: UUID,
    strategy: str,
    limit: int,
) -> list[PerformanceCandidate]:
    ranked = (
        select(
            UrlSnapshot.id.label("snapshot_id"),
            UrlSnapshot.url_id.label("url_id"),
            func.row_number()
            .over(partition_by=UrlSnapshot.url_id, order_by=UrlSnapshot.checked_at.desc())
            .label("position"),
        )
        .join(Url, Url.id == UrlSnapshot.url_id)
        .where(Url.website_id == website_id)
        .subquery()
    )
    records = list(
        db.execute(
            select(Url, UrlSnapshot)
            .join(ranked, ranked.c.url_id == Url.id)
            .join(UrlSnapshot, UrlSnapshot.id == ranked.c.snapshot_id)
            .where(Url.website_id == website_id, ranked.c.position == 1)
        )
    )
    stale_before = datetime.now(UTC) - timedelta(days=MINIMUM_RECHECK_DAYS)
    recent_url_ids = set(
        db.scalars(
            select(PerformanceObservation.url_id).where(
                PerformanceObservation.website_id == website_id,
                PerformanceObservation.strategy == strategy,
                PerformanceObservation.status == "succeeded",
                PerformanceObservation.analyzed_at > stale_before,
            )
        )
    )
    records = [(url, snapshot) for url, snapshot in records if url.id not in recent_url_ids]
    issue_url_ids = set(
        db.scalars(
            select(Issue.url_id).where(
                Issue.website_id == website_id,
                Issue.url_id.is_not(None),
                Issue.status.in_(ACTIVE_ISSUE_STATUSES),
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
    return select_performance_candidates(
        records,
        active_issue_url_ids=issue_url_ids,
        changed_url_ids=changed_url_ids,
        limit=limit,
    )


def _store_failure(
    db: Session,
    *,
    website_id: UUID,
    url: Url,
    strategy: str,
    error_code: str,
    error_message: str,
) -> None:
    db.add(
        PerformanceObservation(
            website_id=website_id,
            url_id=url.id,
            analyzed_at=datetime.now(UTC),
            strategy=strategy,
            status="failed",
            requested_url=url.normalized_url,
            error_code=error_code,
            error_message=error_message,
        )
    )
    db.commit()

import time
from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.routes.reports import build_client_report
from app.core.logging import configure_logging
from app.core.queue import (
    crawl_queue_name,
    enqueue_crawl_job,
    enqueue_integration_sync,
    enqueue_retention_operation,
)
from app.db.session import SessionLocal
from app.models.discovery import CrawlJob
from app.models.integrations import WebsiteIntegration
from app.models.reporting import MonthlyReportSnapshot
from app.models.system import RetentionOperation
from app.models.website import Website, WebsiteSettings
from app.services.crawl_deployment import crawl_deployment_is_active
from app.services.effect_analysis import refresh_due_effect_evaluations

logger = structlog.get_logger()
ACTIVE_CRAWL_STATUSES = (
    "waiting_for_capacity",
    "pending",
    "running",
    "pause_requested",
    "paused",
    "cancel_requested",
)
CRAWL_SCHEDULE = (
    ("full_site_crawl", timedelta(days=7)),
    ("fetch_sitemap", timedelta(days=1)),
    ("light_check", timedelta(days=1)),
)


def schedule_due_jobs() -> int:
    created = 0
    now = datetime.now(UTC)
    with SessionLocal() as db:
        if crawl_deployment_is_active(db):
            logger.info("crawl_scheduling_skipped_deployment_drain")
            return 0
        website_ids = list(
            db.scalars(
                select(Website.id)
                .join(WebsiteSettings, WebsiteSettings.website_id == Website.id)
                .where(Website.status == "active")
                .order_by(WebsiteSettings.queue_priority, Website.id)
            )
        )
        for website_id in website_ids:
            website = db.scalar(select(Website).where(Website.id == website_id).with_for_update())
            if website is None:
                continue
            active_count = int(
                db.scalar(
                    select(func.count(CrawlJob.id)).where(
                        CrawlJob.website_id == website.id,
                        CrawlJob.status.in_(ACTIVE_CRAWL_STATUSES),
                    )
                )
                or 0
            )
            if active_count >= website.settings.crawl_queue_limit:
                db.commit()
                continue
            job_type = _next_due_crawl_type(db, website.id, now)
            if job_type is None:
                db.commit()
                continue
            job = CrawlJob(
                website_id=website.id,
                job_type=job_type,
                settings_snapshot={
                    "max_urls": website.settings.max_urls,
                    "request_delay_ms": website.settings.request_delay_ms,
                    "request_timeout_seconds": website.settings.request_timeout_seconds,
                    "max_response_size": website.settings.max_response_size,
                },
                queue_name=crawl_queue_name(job_type),
                queue_priority=website.settings.queue_priority,
            )
            db.add(job)
            db.commit()
            queued = enqueue_crawl_job(
                str(job.id),
                job_type=job.job_type,
                priority=job.queue_priority,
                website_id=str(job.website_id),
            )
            if queued is False:
                job.status = "waiting_for_capacity"
                db.commit()
                logger.warning(
                    "crawl_waiting_for_queue_capacity",
                    crawl_job_id=str(job.id),
                    website_id=str(job.website_id),
                    queue_name=job.queue_name,
                )
            created += 1
    return created


def dispatch_waiting_crawl_jobs(limit: int = 20) -> int:
    """Offer durable waiting crawls in website-priority order when capacity returns."""
    queued_count = 0
    with SessionLocal() as db:
        if crawl_deployment_is_active(db):
            return 0
        jobs = list(
            db.scalars(
                select(CrawlJob)
                .where(CrawlJob.status == "waiting_for_capacity")
                .order_by(CrawlJob.queue_priority, CrawlJob.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for job in jobs:
            queued = enqueue_crawl_job(
                str(job.id),
                job_type=job.job_type,
                attempt=job.attempt_count,
                priority=job.queue_priority,
                website_id=str(job.website_id),
            )
            if queued is not True:
                continue
            job.status = "pending"
            queued_count += 1
        db.commit()
    return queued_count


def _next_due_crawl_type(db: Session, website_id: UUID, now: datetime) -> str | None:
    latest_by_type: dict[str, CrawlJob] = {}
    for job in db.scalars(
        select(CrawlJob)
        .where(CrawlJob.website_id == website_id)
        .order_by(CrawlJob.created_at.desc())
    ):
        latest_by_type.setdefault(job.job_type, job)

    latest_full = latest_by_type.get("full_site_crawl")
    for job_type, interval in CRAWL_SCHEDULE:
        latest = latest_by_type.get(job_type)
        effective_created_at = latest.created_at if latest else None
        if job_type in {"fetch_sitemap", "light_check"} and latest_full is not None:
            effective_created_at = max(
                value
                for value in (effective_created_at, latest_full.created_at)
                if value is not None
            )
        if effective_created_at is None or _as_utc(effective_created_at) <= now - interval:
            return job_type
    return None


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def schedule_integration_syncs() -> int:
    created = 0
    now = datetime.now(UTC)
    with SessionLocal() as db:
        website_ids = set(
            db.scalars(
                select(WebsiteIntegration.website_id).where(
                    WebsiteIntegration.service.in_(
                        ["search_console", "ga4", "bing_webmaster", "matomo"]
                    ),
                    WebsiteIntegration.status.in_(["active", "error"]),
                )
            )
        )
        for website_id in website_ids:
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
            last_synced = [item.last_synced_at for item in mappings if item.last_synced_at]
            if (
                len(last_synced) == len(mappings)
                and last_synced
                and min(last_synced) > now - timedelta(days=1)
            ):
                continue
            queued_at_values = [
                item.settings.get("sync_queued_at") for item in mappings if item.settings
            ]
            recent_queue = any(
                datetime.fromisoformat(value) > now - timedelta(hours=2)
                for value in queued_at_values
                if isinstance(value, str)
            )
            if recent_queue:
                continue
            queued = enqueue_integration_sync(
                str(website_id),
                job_id=f"integration-sync-{website_id}-{now.date().isoformat()}",
            )
            for mapping in mappings:
                settings = {
                    key: value
                    for key, value in mapping.settings.items()
                    if key not in {"sync_queued_at", "sync_queue_status"}
                }
                if queued:
                    settings["sync_queued_at"] = now.isoformat()
                    settings["sync_queue_status"] = "queued"
                else:
                    settings["sync_queue_status"] = "waiting_for_capacity"
                mapping.settings = settings
            db.commit()
            if not queued:
                logger.warning(
                    "integration_sync_waiting_for_queue_capacity",
                    website_id=str(website_id),
                )
                continue
            created += 1
    return created


def schedule_monthly_report_snapshots() -> int:
    """Freeze the prior calendar month during the first two local days of a new month."""
    local_today = datetime.now(ZoneInfo("Europe/Amsterdam")).date()
    if local_today.day > 2:
        return 0
    period_end = local_today.replace(day=1) - timedelta(days=1)
    period_start = period_end.replace(day=1)
    previous_end = period_start - timedelta(days=1)
    previous_start = previous_end.replace(day=1)
    retention_cutoff = period_start - timedelta(days=3 * 366)
    created = 0
    with SessionLocal() as db:
        websites = list(db.scalars(select(Website).where(Website.status == "active")))
        for website in websites:
            reporting_start = max(website.client.created_at.date(), website.created_at.date())
            if reporting_start > period_start:
                continue
            exists = db.scalar(
                select(MonthlyReportSnapshot.id).where(
                    MonthlyReportSnapshot.website_id == website.id,
                    MonthlyReportSnapshot.period_start == period_start,
                )
            )
            if exists:
                continue
            report = build_client_report(
                website.id,
                "monthly_snapshot",
                period_start,
                period_end,
                previous_start,
                previous_end,
                db,
            )
            db.add(
                MonthlyReportSnapshot(
                    website_id=website.id,
                    period_start=period_start,
                    period_end=period_end,
                    generated_at=datetime.now(UTC),
                    report_data=_json_ready(report),
                )
            )
            db.execute(
                delete(MonthlyReportSnapshot).where(
                    MonthlyReportSnapshot.website_id == website.id,
                    MonthlyReportSnapshot.period_start < retention_cutoff,
                )
            )
            db.commit()
            created += 1
    return created


def schedule_pending_retention_operations() -> int:
    """Requeue due or interrupted retention work without duplicating deletions."""
    now = datetime.now(UTC)
    queued: list[tuple[str, int]] = []
    with SessionLocal() as db:
        operations = list(
            db.scalars(
                select(RetentionOperation)
                .where(
                    RetentionOperation.status.in_(
                        ["pending", "waiting_for_crawl", "failed", "running"]
                    ),
                    (RetentionOperation.next_attempt_at.is_(None))
                    | (RetentionOperation.next_attempt_at <= now),
                )
                .order_by(RetentionOperation.created_at)
                .limit(20)
                .with_for_update(skip_locked=True)
            )
        )
        for operation in operations:
            operation.status = "pending"
            operation.next_attempt_at = now + timedelta(minutes=10)
            queued.append((str(operation.id), operation.attempt_count + 1))
        db.commit()
    for operation_id, attempt in queued:
        enqueue_retention_operation(operation_id, attempt=attempt)
    return len(queued)


def schedule_effect_evaluations() -> int:
    with SessionLocal() as db:
        refreshed = refresh_due_effect_evaluations(db)
        db.commit()
        return refreshed


def _json_ready(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def main() -> None:
    configure_logging()
    while True:
        try:
            waiting_count = dispatch_waiting_crawl_jobs()
            crawl_count = schedule_due_jobs()
            integration_count = schedule_integration_syncs()
            report_count = schedule_monthly_report_snapshots()
            retention_count = schedule_pending_retention_operations()
            effect_count = schedule_effect_evaluations()
            logger.info(
                "scheduler_cycle",
                jobs_created=crawl_count,
                waiting_crawls_queued=waiting_count,
                integration_syncs_created=integration_count,
                report_snapshots_created=report_count,
                retention_operations_queued=retention_count,
                effect_evaluations_refreshed=effect_count,
            )
        except Exception:
            logger.exception("scheduler_cycle_failed")
        time.sleep(60)


if __name__ == "__main__":
    main()

import time
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from rq import Retry
from sqlalchemy import delete, select

from app.api.routes.reports import build_client_report
from app.core.logging import configure_logging
from app.core.queue import get_queue
from app.db.session import SessionLocal
from app.models.discovery import CrawlJob
from app.models.integrations import WebsiteIntegration
from app.models.reporting import MonthlyReportSnapshot
from app.models.website import Website
from app.services.crawl_deployment import crawl_deployment_is_active

logger = structlog.get_logger()


def schedule_due_jobs() -> int:
    created = 0
    now = datetime.now(UTC)
    with SessionLocal() as db:
        if crawl_deployment_is_active(db):
            logger.info("crawl_scheduling_skipped_deployment_drain")
            return 0
        websites = list(db.scalars(select(Website).where(Website.status == "active")))
        for website in websites:
            for job_type, interval in (
                ("fetch_sitemap", timedelta(days=1)),
                ("light_check", timedelta(days=1)),
                ("full_site_crawl", timedelta(days=7)),
            ):
                latest = db.scalar(
                    select(CrawlJob)
                    .where(
                        CrawlJob.website_id == website.id,
                        CrawlJob.job_type == job_type,
                    )
                    .order_by(CrawlJob.created_at.desc())
                    .limit(1)
                )
                if latest and (
                    latest.status in {"pending", "running"} or latest.created_at > now - interval
                ):
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
                )
                db.add(job)
                db.commit()
                get_queue().enqueue(
                    "app.jobs.execute_crawl_job",
                    str(job.id),
                    retry=Retry(max=3, interval=[10, 30, 90]),
                    job_id=str(job.id),
                )
                created += 1
    return created


def schedule_integration_syncs() -> int:
    created = 0
    now = datetime.now(UTC)
    with SessionLocal() as db:
        website_ids = set(
            db.scalars(
                select(WebsiteIntegration.website_id).where(
                    WebsiteIntegration.service.in_(["search_console", "ga4", "bing_webmaster"]),
                    WebsiteIntegration.status.in_(["active", "error"]),
                )
            )
        )
        for website_id in website_ids:
            mappings = list(
                db.scalars(
                    select(WebsiteIntegration).where(
                        WebsiteIntegration.website_id == website_id,
                        WebsiteIntegration.service.in_(["search_console", "ga4", "bing_webmaster"]),
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
            for mapping in mappings:
                mapping.settings = {**mapping.settings, "sync_queued_at": now.isoformat()}
            db.commit()
            get_queue().enqueue(
                "app.services.integration_sync.synchronize_website_integrations",
                str(website_id),
                retry=Retry(max=3, interval=[60, 300, 900]),
                job_id=f"integration-sync-{website_id}-{now.date().isoformat()}",
            )
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
            crawl_count = schedule_due_jobs()
            integration_count = schedule_integration_syncs()
            report_count = schedule_monthly_report_snapshots()
            logger.info(
                "scheduler_cycle",
                jobs_created=crawl_count,
                integration_syncs_created=integration_count,
                report_snapshots_created=report_count,
            )
        except Exception:
            logger.exception("scheduler_cycle_failed")
        time.sleep(60)


if __name__ == "__main__":
    main()

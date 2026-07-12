import time
from datetime import UTC, datetime, timedelta

import structlog
from rq import Retry
from sqlalchemy import select

from app.core.logging import configure_logging
from app.core.queue import get_queue
from app.db.session import SessionLocal
from app.models.discovery import CrawlJob
from app.models.integrations import WebsiteIntegration
from app.models.website import Website

logger = structlog.get_logger()


def schedule_due_jobs() -> int:
    created = 0
    now = datetime.now(UTC)
    with SessionLocal() as db:
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
                    WebsiteIntegration.service.in_(["search_console", "ga4"]),
                    WebsiteIntegration.status.in_(["active", "error"]),
                )
            )
        )
        for website_id in website_ids:
            mappings = list(
                db.scalars(
                    select(WebsiteIntegration).where(
                        WebsiteIntegration.website_id == website_id,
                        WebsiteIntegration.service.in_(["search_console", "ga4"]),
                    )
                )
            )
            last_synced = [item.last_synced_at for item in mappings if item.last_synced_at]
            if last_synced and min(last_synced) > now - timedelta(days=1):
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


def main() -> None:
    configure_logging()
    while True:
        try:
            crawl_count = schedule_due_jobs()
            integration_count = schedule_integration_syncs()
            logger.info(
                "scheduler_cycle",
                jobs_created=crawl_count,
                integration_syncs_created=integration_count,
            )
        except Exception:
            logger.exception("scheduler_cycle_failed")
        time.sleep(60)


if __name__ == "__main__":
    main()

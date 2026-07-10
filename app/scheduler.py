import time
from datetime import UTC, datetime, timedelta

import structlog
from rq import Retry
from sqlalchemy import select

from app.core.logging import configure_logging
from app.core.queue import get_queue
from app.db.session import SessionLocal
from app.models.discovery import CrawlJob
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


def main() -> None:
    configure_logging()
    while True:
        try:
            count = schedule_due_jobs()
            logger.info("scheduler_cycle", jobs_created=count)
        except Exception:
            logger.exception("scheduler_cycle_failed")
        time.sleep(60)


if __name__ == "__main__":
    main()

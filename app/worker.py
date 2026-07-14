import os
from datetime import UTC, datetime

from rq import Worker
from sqlalchemy import select

from app.core.logging import configure_logging
from app.core.queue import get_redis
from app.db.session import SessionLocal
from app.models.crawl import CrawlRun
from app.models.discovery import CrawlJob


def recover_interrupted_crawls() -> None:
    with SessionLocal() as db:
        jobs = list(
            db.scalars(
                select(CrawlJob).where(
                    CrawlJob.status.in_(["running", "pause_requested", "cancel_requested"])
                )
            )
        )
        for job in jobs:
            run = db.scalar(select(CrawlRun).where(CrawlRun.crawl_job_id == job.id))
            if job.status == "cancel_requested":
                finished = datetime.now(UTC)
                job.status = "cancelled"
                job.finished_at = finished
                if run:
                    run.status = "cancelled"
                    run.finished_at = finished
            else:
                job.status = "paused"
                job.error_message = "Worker opnieuw gestart; crawl kan veilig worden hervat."
                if run:
                    run.status = "paused"
        db.commit()


def main() -> None:
    configure_logging()
    queues = [name.strip() for name in os.getenv("WORKER_QUEUES", "default").split(",")]
    if "default" in queues:
        recover_interrupted_crawls()
    Worker(queues, connection=get_redis()).work()


if __name__ == "__main__":
    main()

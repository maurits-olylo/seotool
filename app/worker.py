import os
import socket
from datetime import UTC, datetime

from redis import Redis
from rq import Worker
from sqlalchemy import select

from app.core.logging import configure_logging
from app.core.queue import CRAWL_QUEUES, LIGHT_CRAWL_QUEUE, get_redis
from app.db.session import SessionLocal
from app.models.crawl import CrawlRun
from app.models.discovery import CrawlJob


def worker_name(configured_name: str | None = None, hostname: str | None = None) -> str | None:
    """Keep the configured role recognizable while making each container registration unique."""
    role = (
        configured_name if configured_name is not None else os.getenv("WORKER_NAME", "")
    ).strip()
    if not role:
        return None
    container = (hostname if hostname is not None else socket.gethostname()).strip()
    return f"{role}-{container}" if container else role


def worker_is_registered(
    connection: Redis | None = None,
    *,
    name: str | None = None,
) -> bool:
    """Report healthy only after this exact worker has registered as active in RQ."""
    registration_name = name if name is not None else worker_name()
    if not registration_name:
        return False
    redis = connection if connection is not None else get_redis()
    key = f"rq:worker:{registration_name}"
    return bool(redis.exists(key) and not redis.hexists(key, "death"))


def active_crawl_job_ids() -> set[str]:
    """Return crawl IDs currently owned by another live RQ worker."""
    active: set[str] = set()
    for worker in Worker.all(connection=get_redis()):
        try:
            current = worker.get_current_job()
        except Exception:
            continue
        if current is None or current.func_name != "app.jobs.execute_crawl_job":
            continue
        if current.args:
            active.add(str(current.args[0]))
    return active


def recover_interrupted_crawls(active_job_ids: set[str] | None = None) -> None:
    protected = active_crawl_job_ids() if active_job_ids is None else active_job_ids
    with SessionLocal() as db:
        jobs = list(
            db.scalars(
                select(CrawlJob).where(
                    CrawlJob.status.in_(["running", "pause_requested", "cancel_requested"])
                )
            )
        )
        for job in jobs:
            if str(job.id) in protected:
                continue
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
    queues = [name.strip() for name in os.getenv("WORKER_QUEUES", LIGHT_CRAWL_QUEUE).split(",")]
    if CRAWL_QUEUES.intersection(queues):
        recover_interrupted_crawls()
    Worker(
        queues,
        connection=get_redis(),
        name=worker_name(),
    ).work(with_scheduler=True)


if __name__ == "__main__":
    main()

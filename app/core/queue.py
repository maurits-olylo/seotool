from redis import Redis
from rq import Queue, Retry

from app.core.config import get_settings


def get_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def get_queue(name: str = "default") -> Queue:
    return Queue(name, connection=get_redis(), default_timeout=3600)


def enqueue_crawl_job(job_id: str, *, attempt: int = 0) -> None:
    queue_job_id = job_id if attempt == 0 else f"{job_id}-resume-{attempt}"
    get_queue().enqueue(
        "app.jobs.execute_crawl_job",
        job_id,
        retry=Retry(max=3, interval=[10, 30, 90]),
        job_id=queue_job_id,
        job_timeout=21_600,
    )

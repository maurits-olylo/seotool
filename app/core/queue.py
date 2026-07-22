from redis import Redis
from rq import Queue, Retry

from app.core.config import get_settings

CRAWL_QUEUE = "crawls"
INTEGRATION_QUEUE = "integrations"
EXPORT_QUEUE = "exports"


def get_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def get_queue(name: str) -> Queue:
    return Queue(name, connection=get_redis(), default_timeout=3600)


def enqueue_crawl_job(job_id: str, *, attempt: int = 0) -> None:
    queue_job_id = job_id if attempt == 0 else f"{job_id}-resume-{attempt}"
    get_queue(CRAWL_QUEUE).enqueue(
        "app.jobs.execute_crawl_job",
        job_id,
        retry=Retry(max=3, interval=[10, 30, 90]),
        job_id=queue_job_id,
        job_timeout=21_600,
    )


def enqueue_integration_sync(
    website_id: str,
    days: int | None = None,
    *,
    job_id: str,
) -> None:
    args: tuple[object, ...] = (website_id,) if days is None else (website_id, days)
    get_queue(INTEGRATION_QUEUE).enqueue(
        "app.services.integration_sync.synchronize_website_integrations",
        *args,
        retry=Retry(max=3, interval=[60, 300, 900]),
        job_id=job_id,
        job_timeout=21_600,
    )

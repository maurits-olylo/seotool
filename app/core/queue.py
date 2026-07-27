from dataclasses import dataclass

from redis import Redis
from rq import Queue, Retry, Worker

from app.core.config import get_settings

LIGHT_CRAWL_QUEUE = "crawls_light"
FULL_CRAWL_QUEUE = "crawls_full"
CRAWL_QUEUES = frozenset({LIGHT_CRAWL_QUEUE, FULL_CRAWL_QUEUE})
LEGACY_CRAWL_QUEUE = "crawls"
INTEGRATION_QUEUE = "integrations"
EXPORT_QUEUE = "exports"


@dataclass(frozen=True)
class CrawlQueueState:
    position: int | None
    queued_jobs: int
    workers: int


def get_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def get_queue(name: str) -> Queue:
    return Queue(name, connection=get_redis(), default_timeout=3600)


def crawl_queue_name(job_type: str) -> str:
    return (
        FULL_CRAWL_QUEUE
        if job_type in {"full_site_crawl", "recalculate_issues"}
        else LIGHT_CRAWL_QUEUE
    )


def enqueue_crawl_job(job_id: str, *, job_type: str, attempt: int = 0) -> None:
    queue_job_id = job_id if attempt == 0 else f"{job_id}-resume-{attempt}"
    get_queue(crawl_queue_name(job_type)).enqueue(
        "app.jobs.execute_crawl_job",
        job_id,
        retry=Retry(max=3, interval=[10, 30, 90]),
        job_id=queue_job_id,
        job_timeout=21_600,
    )


def crawl_queue_state(job_id: str, *, job_type: str) -> CrawlQueueState:
    """Return the visible FIFO position for an initial or resumed crawl job."""
    connection = get_redis()
    queue_name = crawl_queue_name(job_type)
    queue = Queue(queue_name, connection=connection)
    queued_ids = queue.get_job_ids()
    position = next(
        (
            index
            for index, queued_id in enumerate(queued_ids, start=1)
            if queued_id == job_id or queued_id.startswith(f"{job_id}-resume-")
        ),
        None,
    )
    workers = sum(
        queue_name in _worker_queue_names(worker)
        for worker in Worker.all(connection=connection)
    )
    return CrawlQueueState(position=position, queued_jobs=len(queued_ids), workers=workers)


def _worker_queue_names(worker: Worker) -> set[str]:
    names = getattr(worker, "queue_names", [])
    if callable(names):
        names = names()
    return {str(name) for name in names}


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

from dataclasses import dataclass

from redis import Redis
from rq import Queue, Retry, Worker

from app.core.config import get_settings
from app.services.queue_policy import (
    DEFAULT_WEBSITE_PRIORITY,
    MIN_WEBSITE_PRIORITY,
    queue_policy,
)

LIGHT_CRAWL_QUEUE = "crawls_light"
FULL_CRAWL_QUEUE = "crawls_full"
CRAWL_QUEUES = frozenset({LIGHT_CRAWL_QUEUE, FULL_CRAWL_QUEUE})
LEGACY_CRAWL_QUEUE = "crawls"
INTEGRATION_QUEUE = "integrations"
EXPORT_QUEUE = "exports"
VERIFICATION_QUEUE = "verifications"
MAINTENANCE_QUEUE = "maintenance"
SITEMAP_QUEUE = "sitemaps"


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
    if job_type == "fetch_sitemap":
        return SITEMAP_QUEUE
    return (
        FULL_CRAWL_QUEUE
        if job_type in {"full_site_crawl", "recalculate_issues"}
        else LIGHT_CRAWL_QUEUE
    )


def queue_has_capacity(name: str) -> bool:
    policy = queue_policy(name)
    return policy.enabled and get_queue(name).count < policy.admission_backlog


def _enqueue(
    queue_name: str,
    function: str,
    *args: object,
    job_id: str,
    priority: int = DEFAULT_WEBSITE_PRIORITY,
    meta: dict[str, object] | None = None,
) -> bool:
    policy = queue_policy(queue_name)
    queue = get_queue(queue_name)
    if not policy.enabled or queue.count >= policy.admission_backlog:
        return False
    queue.enqueue(
        function,
        *args,
        retry=Retry(max=len(policy.retry_intervals), interval=list(policy.retry_intervals)),
        job_id=job_id,
        job_timeout=policy.job_timeout_seconds,
        at_front=priority == MIN_WEBSITE_PRIORITY,
        meta={
            "queue_policy_version": "2026-08-02-v1",
            "priority": priority,
            "max_attempts": len(policy.retry_intervals) + 1,
            **(meta or {}),
        },
        on_failure="app.services.queue_failures.record_dead_letter",
    )
    return True


def enqueue_crawl_job(
    job_id: str,
    *,
    job_type: str,
    attempt: int = 0,
    priority: int = DEFAULT_WEBSITE_PRIORITY,
    website_id: str | None = None,
) -> bool:
    queue_job_id = job_id if attempt == 0 else f"{job_id}-resume-{attempt}"
    return _enqueue(
        crawl_queue_name(job_type),
        "app.jobs.execute_crawl_job",
        job_id,
        job_id=queue_job_id,
        priority=priority,
        meta={"website_id": website_id, "job_type": job_type, "crawl_job_id": job_id},
    )


def enqueue_recommendation_verification(
    verification_id: str, *, website_id: str | None = None, priority: int = 50
) -> bool:
    return _enqueue(
        VERIFICATION_QUEUE,
        "app.services.recommendation_verifications.execute_verification",
        verification_id,
        job_id=f"recommendation-verification-{verification_id}",
        priority=priority,
        meta={"website_id": website_id, "job_type": "recommendation_verification"},
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
        queue_name in _worker_queue_names(worker) for worker in Worker.all(connection=connection)
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
) -> bool:
    args: tuple[object, ...] = (website_id,) if days is None else (website_id, days)
    return _enqueue(
        INTEGRATION_QUEUE,
        "app.services.integration_sync.synchronize_website_integrations",
        *args,
        job_id=job_id,
        meta={"website_id": website_id, "job_type": "integration_sync"},
    )


def enqueue_retention_operation(operation_id: str, *, attempt: int = 0) -> bool:
    return _enqueue(
        MAINTENANCE_QUEUE,
        "app.services.retention_operations.execute_retention_operation",
        operation_id,
        job_id=f"retention-{operation_id}-{attempt}",
        meta={"job_type": "retention_operation"},
    )


def enqueue_export(export_id: str, *, website_id: str) -> bool:
    return _enqueue(
        EXPORT_QUEUE,
        "app.services.exports.generate_export",
        export_id,
        job_id=f"export-{export_id}",
        meta={"website_id": website_id, "job_type": "generate_export"},
    )

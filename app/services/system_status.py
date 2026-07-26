from typing import Any

from redis import Redis
from rq import Queue, Worker

from app.core.queue import (
    CRAWL_QUEUES,
    EXPORT_QUEUE,
    FULL_CRAWL_QUEUE,
    INTEGRATION_QUEUE,
    LIGHT_CRAWL_QUEUE,
    get_redis,
)


def _worker_queue_names(worker: Worker) -> set[str]:
    names = getattr(worker, "queue_names", [])
    if callable(names):
        names = names()
    return {str(name) for name in names}


def build_queue_status(redis: Redis | None = None) -> dict[str, Any]:
    """Return a small operational snapshot without exposing worker internals."""
    connection = redis or get_redis()
    connection.ping()
    workers = Worker.all(connection=connection)
    queues: dict[str, dict[str, int | str]] = {}
    for name in (*sorted(CRAWL_QUEUES), INTEGRATION_QUEUE, EXPORT_QUEUE):
        worker_count = sum(name in _worker_queue_names(worker) for worker in workers)
        queues[name] = {
            "status": "ok" if worker_count else "unavailable",
            "workers": worker_count,
            "queued_jobs": Queue(name, connection=connection).count,
        }
    queues["crawls"] = {
        "status": (
            "ok"
            if queues[LIGHT_CRAWL_QUEUE]["status"] == "ok"
            and queues[FULL_CRAWL_QUEUE]["status"] == "ok"
            else "unavailable"
        ),
        "workers": sum(
            any(queue_name in _worker_queue_names(worker) for queue_name in CRAWL_QUEUES)
            for worker in workers
        ),
        "queued_jobs": sum(int(queues[name]["queued_jobs"]) for name in CRAWL_QUEUES),
    }
    return {"redis": "ok", "queues": queues}

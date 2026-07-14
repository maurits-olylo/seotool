from typing import Any

from redis import Redis
from rq import Queue, Worker

from app.core.queue import get_redis


def _worker_queue_names(worker: Worker) -> set[str]:
    names = getattr(worker, "queue_names", [])
    return {str(name) for name in names}


def build_queue_status(redis: Redis | None = None) -> dict[str, Any]:
    """Return a small operational snapshot without exposing worker internals."""
    connection = redis or get_redis()
    connection.ping()
    workers = Worker.all(connection=connection)
    queues: dict[str, dict[str, int | str]] = {}
    for name in ("default", "exports"):
        worker_count = sum(name in _worker_queue_names(worker) for worker in workers)
        queues[name] = {
            "status": "ok" if worker_count else "unavailable",
            "workers": worker_count,
            "queued_jobs": Queue(name, connection=connection).count,
        }
    return {"redis": "ok", "queues": queues}

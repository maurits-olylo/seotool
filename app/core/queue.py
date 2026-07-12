from redis import Redis
from rq import Queue

from app.core.config import get_settings


def get_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def get_queue(name: str = "default") -> Queue:
    return Queue(name, connection=get_redis(), default_timeout=3600)

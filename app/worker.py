import os

from rq import Worker

from app.core.logging import configure_logging
from app.core.queue import get_redis


def main() -> None:
    configure_logging()
    queues = [name.strip() for name in os.getenv("WORKER_QUEUES", "default").split(",")]
    Worker(queues, connection=get_redis()).work()


if __name__ == "__main__":
    main()

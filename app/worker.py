from rq import Worker

from app.core.logging import configure_logging
from app.core.queue import get_redis


def main() -> None:
    configure_logging()
    Worker(["default"], connection=get_redis()).work()


if __name__ == "__main__":
    main()

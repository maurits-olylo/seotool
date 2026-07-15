import argparse
import sys

from app.core.logging import configure_logging
from app.core.queue import enqueue_crawl_job
from app.db.session import SessionLocal
from app.services.crawl_deployment import (
    deployment_drain_status,
    finish_deployment_drain,
    start_deployment_drain,
    wait_for_deployment_drain,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Veilige deploymentbesturing voor crawls")
    commands = parser.add_subparsers(dest="command", required=True)
    pause = commands.add_parser("pause-crawls", help="Blokkeer en pauzeer alle crawls")
    pause.add_argument("--wait", action="store_true", help="Wacht tot actieve URLs klaar zijn")
    pause.add_argument("--timeout", type=float, default=300.0)
    commands.add_parser("status", help="Toon de deploymentpauzestatus")
    commands.add_parser("resume-crawls", help="Hervat alleen deployment-gepauzeerde crawls")
    return parser


def _status_line(status) -> str:  # type: ignore[no-untyped-def]
    return (
        f"active={str(status.active).lower()} safe={str(status.safe).lower()} "
        f"tracked={len(status.tracked_job_ids)} waiting={len(status.waiting_job_ids)}"
    )


def main() -> int:
    configure_logging()
    args = _parser().parse_args()
    if args.command == "pause-crawls":
        with SessionLocal() as db:
            status = start_deployment_drain(db)
        if args.wait and not status.safe:
            try:
                status = wait_for_deployment_drain(SessionLocal, timeout_seconds=args.timeout)
            except TimeoutError as exc:
                print(str(exc), file=sys.stderr)
                return 1
        print(_status_line(status))
        return 0 if status.safe or not args.wait else 1
    if args.command == "status":
        with SessionLocal() as db:
            status = deployment_drain_status(db)
        print(_status_line(status))
        return 0
    try:
        with SessionLocal() as db:
            resumed = finish_deployment_drain(db)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for job_id, attempt in resumed:
        enqueue_crawl_job(job_id, attempt=attempt)
    print(f"active=false resumed={len(resumed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

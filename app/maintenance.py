import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from uuid import UUID

from sqlalchemy import select

from app.core.logging import configure_logging
from app.core.queue import enqueue_crawl_job
from app.db.session import SessionLocal
from app.models.crawl import CrawlRun
from app.services.change_history import change_history_counts, reset_change_history
from app.services.crawl_deployment import (
    deployment_drain_status,
    finish_deployment_drain,
    start_deployment_drain,
    wait_for_deployment_drain,
)
from app.services.privacy_deletions import apply_privacy_deletions
from app.services.retention_audit import build_retention_audit, cleanup_element_locations
from app.services.retention_operations import (
    create_retention_operations,
    execute_retention_operation,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Veilige deploymentbesturing voor crawls")
    commands = parser.add_subparsers(dest="command", required=True)
    pause = commands.add_parser("pause-crawls", help="Blokkeer en pauzeer alle crawls")
    pause.add_argument("--wait", action="store_true", help="Wacht tot actieve URLs klaar zijn")
    pause.add_argument("--timeout", type=float, default=300.0)
    commands.add_parser("status", help="Toon de deploymentpauzestatus")
    commands.add_parser("resume-crawls", help="Hervat alleen deployment-gepauzeerde crawls")
    audit = commands.add_parser(
        "retention-audit",
        help="Toon read-only bewaartermijn- en groeikandidaten",
    )
    audit.add_argument(
        "--as-of",
        type=date.fromisoformat,
        help="Peildatum als YYYY-MM-DD (standaard: vandaag)",
    )
    cleanup = commands.add_parser(
        "cleanup-element-locations",
        help="Verwijder veilig oude, probleemvrije elementlocaties",
    )
    cleanup.add_argument("--batch-size", type=int, default=10_000)
    cleanup.add_argument("--website-id", type=UUID)
    cleanup.add_argument(
        "--max-rows",
        type=int,
        default=50_000,
        help="Harde limiet per uitvoering (standaard: 50000)",
    )
    cleanup.add_argument(
        "--confirm-delete",
        action="store_true",
        help="Verplichte expliciete bevestiging voor verwijdering",
    )
    commands.add_parser(
        "change-history-audit",
        help="Toon read-only aantallen in de wijzigingshistorie",
    )
    commands.add_parser(
        "reapply-privacy-deletions",
        help="Pas het onafhankelijke privacyverwijderingsregister opnieuw toe",
    )
    retention_all = commands.add_parser(
        "retention-all",
        help="Maak en hervat retentieoperaties voor alle websites",
    )
    retention_all.add_argument("--batch-size", type=int, default=10_000)
    retention_all.add_argument("--max-rows-per-operation", type=int, default=50_000)
    reset_changes = commands.add_parser(
        "reset-change-history",
        help="Verwijder wijzigingsrecords zonder snapshots, issues of crawls te verwijderen",
    )
    reset_changes.add_argument("--website-id", type=UUID)
    reset_changes.add_argument(
        "--confirm-delete",
        action="store_true",
        help="Verplichte expliciete bevestiging voor verwijdering",
    )
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
    if args.command == "retention-audit":
        with SessionLocal() as db:
            result = build_retention_audit(db, as_of=args.as_of)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.command == "change-history-audit":
        with SessionLocal() as db:
            result = change_history_counts(db)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.command == "reapply-privacy-deletions":
        try:
            with SessionLocal() as db:
                result = apply_privacy_deletions(db)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.command == "retention-all":
        with SessionLocal() as db:
            latest_runs = list(
                db.scalars(
                    select(CrawlRun)
                    .where(
                        CrawlRun.crawl_type == "full_site_crawl",
                        CrawlRun.status.in_(["succeeded", "partially_succeeded"]),
                    )
                    .order_by(CrawlRun.website_id, CrawlRun.started_at.desc())
                )
            )
            operations = []
            seen = set()
            for run in latest_runs:
                if run.website_id in seen:
                    continue
                seen.add(run.website_id)
                operations.extend(
                    str(operation.id) for operation in create_retention_operations(db, run.id)
                )
        results = [
            asdict(
                execute_retention_operation(
                    operation_id,
                    batch_size=args.batch_size,
                    max_rows=args.max_rows_per_operation,
                )
            )
            for operation_id in operations
        ]
        print(json.dumps({"operations": results}, indent=2, ensure_ascii=False))
        return 0
    if args.command == "reset-change-history":
        if not args.confirm_delete:
            print(
                "Gebruik --confirm-delete om de verwijdering expliciet te bevestigen.",
                file=sys.stderr,
            )
            return 2
        try:
            with SessionLocal() as db:
                result = reset_change_history(db, website_id=args.website_id)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps(asdict(result), indent=2, ensure_ascii=False))
        return 0
    if args.command == "cleanup-element-locations":
        if not args.confirm_delete:
            print(
                "Gebruik --confirm-delete om de opschoning expliciet te bevestigen.",
                file=sys.stderr,
            )
            return 2

        def report_batch(website: str, deleted: int, total: int) -> None:
            print(f"website={website!r} batch_deleted={deleted} total_deleted={total}", flush=True)

        try:
            with SessionLocal() as db:
                result = cleanup_element_locations(
                    db,
                    batch_size=args.batch_size,
                    website_id=args.website_id,
                    max_rows=args.max_rows,
                    on_batch=report_batch,
                )
        except (RuntimeError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps(asdict(result), indent=2, ensure_ascii=False))
        return 0
    try:
        with SessionLocal() as db:
            resumed = finish_deployment_drain(db)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for job_id, job_type, attempt in resumed:
        enqueue_crawl_job(job_id, job_type=job_type, attempt=attempt)
    print(f"active=false resumed={len(resumed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.common import utc_now
from app.models.crawl import CrawlRun, ElementLocation
from app.models.discovery import CrawlJob
from app.models.system import RetentionOperation
from app.models.website import Website
from app.services.retention_audit import (
    COMPLETED_FULL_CRAWL_STATUSES,
    element_location_candidate_ids,
)

logger = structlog.get_logger()
ACTIVE_CRAWL_STATUSES = ("pending", "running", "pause_requested", "paused", "cancel_requested")
RETRY_DELAY = timedelta(minutes=10)
RUNNING_TIMEOUT = timedelta(hours=1)


@dataclass(frozen=True)
class RetentionRunResult:
    operation_id: str
    status: str
    deleted: int
    batches: int
    candidates_remaining: int | None


def create_retention_operation(db: Session, crawl_run_id: UUID) -> RetentionOperation | None:
    """Create exactly one operation for a completed full-site crawl."""
    run = db.get(CrawlRun, crawl_run_id)
    if (
        run is None
        or run.crawl_type != "full_site_crawl"
        or run.status not in COMPLETED_FULL_CRAWL_STATUSES
    ):
        return None
    existing = db.scalar(
        select(RetentionOperation).where(RetentionOperation.trigger_crawl_run_id == crawl_run_id)
    )
    if existing is not None:
        return existing
    operation = RetentionOperation(
        website_id=run.website_id,
        trigger_crawl_run_id=run.id,
        status="pending",
        next_attempt_at=utc_now(),
    )
    db.add(operation)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return db.scalar(
            select(RetentionOperation).where(
                RetentionOperation.trigger_crawl_run_id == crawl_run_id
            )
        )
    db.refresh(operation)
    return operation


def execute_retention_operation(
    operation_id: str,
    *,
    batch_size: int = 10_000,
    max_rows: int = 50_000,
) -> RetentionRunResult:
    """Run bounded, idempotent batches and persist progress after every commit."""
    if batch_size < 1 or batch_size > 50_000:
        raise ValueError("batch_size must be between 1 and 50000")
    if max_rows < 1 or max_rows > 1_000_000:
        raise ValueError("max_rows must be between 1 and 1000000")

    operation_uuid = uuid.UUID(operation_id)
    deleted_this_run = 0
    batches_this_run = 0
    try:
        while deleted_this_run < max_rows:
            with SessionLocal() as db:
                operation = db.scalar(
                    select(RetentionOperation)
                    .where(RetentionOperation.id == operation_uuid)
                    .with_for_update()
                )
                if operation is None:
                    raise RuntimeError("Retention operation does not exist")
                if operation.status == "succeeded":
                    return _result(operation, deleted_this_run, batches_this_run)
                website = db.scalar(
                    select(Website).where(Website.id == operation.website_id).with_for_update()
                )
                if website is None:
                    raise RuntimeError("Retention website does not exist")
                active_crawl = db.scalar(
                    select(CrawlJob.id).where(
                        CrawlJob.website_id == operation.website_id,
                        CrawlJob.status.in_(ACTIVE_CRAWL_STATUSES),
                    )
                )
                if active_crawl is not None:
                    operation.status = "waiting_for_crawl"
                    operation.next_attempt_at = utc_now() + RETRY_DELAY
                    operation.error_message = None
                    db.commit()
                    return _result(operation, deleted_this_run, batches_this_run)

                operation.status = "running"
                operation.started_at = operation.started_at or utc_now()
                operation.attempt_count += 1 if batches_this_run == 0 else 0
                operation.error_message = None
                operation.next_attempt_at = utc_now() + RUNNING_TIMEOUT
                ids = element_location_candidate_ids(
                    db,
                    operation.website_id,
                    limit=min(batch_size, max_rows - deleted_this_run),
                )
                if not ids:
                    operation.status = "succeeded"
                    operation.candidates_remaining = 0
                    operation.finished_at = utc_now()
                    operation.next_attempt_at = None
                    db.commit()
                    logger.info(
                        "retention_operation_succeeded",
                        operation_id=operation_id,
                        website_id=str(operation.website_id),
                        rows_deleted=operation.rows_deleted,
                        batches_completed=operation.batches_completed,
                    )
                    return _result(operation, deleted_this_run, batches_this_run)

                db.execute(delete(ElementLocation).where(ElementLocation.id.in_(ids)))
                batch_deleted = len(ids)
                operation.rows_deleted += batch_deleted
                operation.batches_completed += 1
                operation.candidates_remaining = None
                operation.next_attempt_at = utc_now() + RUNNING_TIMEOUT
                db.commit()
                deleted_this_run += batch_deleted
                batches_this_run += 1
                logger.info(
                    "retention_batch_completed",
                    operation_id=operation_id,
                    website_id=str(operation.website_id),
                    batch_deleted=batch_deleted,
                    total_deleted=operation.rows_deleted,
                )

        with SessionLocal() as db:
            operation = db.get(RetentionOperation, operation_uuid)
            if operation is None:
                raise RuntimeError("Retention operation does not exist")
            operation.status = "pending"
            operation.next_attempt_at = utc_now() + RETRY_DELAY
            db.commit()
            logger.warning(
                "retention_operation_limit_reached",
                operation_id=operation_id,
                website_id=str(operation.website_id),
                deleted_this_run=deleted_this_run,
                rows_deleted=operation.rows_deleted,
            )
            return _result(operation, deleted_this_run, batches_this_run)
    except Exception as exc:
        with SessionLocal() as db:
            operation = db.get(RetentionOperation, operation_uuid)
            if operation is not None:
                operation.status = "failed"
                operation.error_message = str(exc)[:4000]
                operation.next_attempt_at = datetime.now(UTC) + RETRY_DELAY
                db.commit()
        logger.exception("retention_operation_failed", operation_id=operation_id)
        raise


def _result(operation: RetentionOperation, deleted: int, batches: int) -> RetentionRunResult:
    return RetentionRunResult(
        operation_id=str(operation.id),
        status=operation.status,
        deleted=deleted,
        batches=batches,
        candidates_remaining=operation.candidates_remaining,
    )

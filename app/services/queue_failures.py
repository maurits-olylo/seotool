from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.models.system import QueueDeadLetter

logger = structlog.get_logger()


def record_dead_letter(
    job: Any,
    _connection: Any,
    _exc_type: type[BaseException],
    exc_value: BaseException,
    _traceback: Any,
) -> None:
    """Persist terminal RQ failures; retryable failures remain only in RQ."""
    if bool(getattr(job, "should_retry", False)):
        return
    try:
        meta = dict(getattr(job, "meta", {}) or {})
        website_id = _uuid_or_none(meta.get("website_id"))
        queue_name = str(getattr(job, "origin", "unknown"))
        original_job_id = str(getattr(job, "id", "unknown"))
        with SessionLocal() as db:
            record = db.scalar(
                select(QueueDeadLetter).where(
                    QueueDeadLetter.queue_name == queue_name,
                    QueueDeadLetter.original_job_id == original_job_id,
                )
            )
            record = record or QueueDeadLetter(
                queue_name=queue_name,
                original_job_id=original_job_id,
                job_type=str(meta.get("job_type") or getattr(job, "func_name", "unknown")),
                failed_at=datetime.now(UTC),
                error_message=str(exc_value)[:4000] or type(exc_value).__name__,
            )
            record.website_id = website_id
            record.attempt_count = int(meta.get("max_attempts", 1))
            record.payload = {key: value for key, value in meta.items() if value is not None}
            db.add(record)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
        logger.error(
            "queue_job_dead_lettered",
            queue_name=queue_name,
            job_id=original_job_id,
            job_type=record.job_type,
        )
    except Exception:
        logger.exception("queue_dead_letter_persistence_failed")


def _uuid_or_none(value: object) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except ValueError:
        return None

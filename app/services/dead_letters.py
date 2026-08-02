from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.queue import (
    EXPORT_QUEUE,
    VERIFICATION_QUEUE,
    enqueue_crawl_job,
    enqueue_export,
    enqueue_integration_sync,
    enqueue_recommendation_verification,
    enqueue_retention_operation,
    queue_has_capacity,
)
from app.models.common import utc_now
from app.models.discovery import CrawlJob
from app.models.exports import Export
from app.models.recommendations import RecommendationTask, RecommendationVerification
from app.models.system import QueueDeadLetter


class DeadLetterError(RuntimeError):
    pass


def requeue_dead_letter(db: Session, record: QueueDeadLetter) -> None:
    if record.status != "unresolved":
        raise DeadLetterError("Alleen een onopgeloste dead letter kan opnieuw worden aangeboden.")
    queued = _requeue(db, record)
    if not queued:
        raise DeadLetterError("De doelwachtrij heeft momenteel onvoldoende capaciteit.")
    record.status = "requeued"
    record.resolved_at = utc_now()
    record.resolution = "Gecontroleerd opnieuw aangeboden vanuit dead-letterbeheer."
    db.commit()


def resolve_dead_letter(db: Session, record: QueueDeadLetter, resolution: str) -> None:
    if record.status != "unresolved":
        raise DeadLetterError("Deze dead letter is al afgehandeld.")
    cleaned = resolution.strip()
    if not cleaned:
        raise DeadLetterError("Een toelichting is verplicht.")
    record.status = "resolved"
    record.resolved_at = utc_now()
    record.resolution = cleaned[:4000]
    db.commit()


def _requeue(db: Session, record: QueueDeadLetter) -> bool:
    payload = record.payload
    if record.job_type in {
        "fetch_sitemap",
        "light_check",
        "full_page_analysis",
        "full_site_crawl",
        "recalculate_issues",
    }:
        job = _get(db, CrawlJob, payload.get("crawl_job_id"), "crawltaak")
        if job.status in {"running", "pause_requested", "cancel_requested"}:
            raise DeadLetterError(
                "De crawltaak is nog actief en kan niet opnieuw worden aangeboden."
            )
        queued = enqueue_crawl_job(
            str(job.id),
            job_type=job.job_type,
            attempt=job.attempt_count + 1,
            priority=job.queue_priority,
            website_id=str(job.website_id),
        )
        job.status = "pending" if queued else "waiting_for_capacity"
        job.finished_at = None
        job.error_message = None
        return queued
    if record.job_type == "integration_sync":
        website_id = str(payload.get("website_id") or "")
        if not website_id:
            raise DeadLetterError("Website-ID ontbreekt in het dead-letterbewijs.")
        days = payload.get("days")
        return enqueue_integration_sync(
            website_id,
            int(days) if days is not None else None,
            job_id=f"dead-letter-{record.id}",
        )
    if record.job_type == "retention_operation":
        operation_id = str(payload.get("operation_id") or "")
        if not operation_id:
            raise DeadLetterError("Retentieoperatie ontbreekt in het dead-letterbewijs.")
        return enqueue_retention_operation(operation_id, attempt=record.attempt_count + 1)
    if record.job_type == "generate_export":
        export = _get(db, Export, payload.get("export_id"), "export")
        if not queue_has_capacity(EXPORT_QUEUE):
            return False
        export.status = "pending"
        export.error_message = None
        export.finished_at = None
        db.commit()
        queued = enqueue_export(str(export.id), website_id=str(export.website_id))
        if not queued:
            export.status = "failed"
            export.error_message = "De exportwachtrij is tijdelijk vol"
            db.commit()
        return queued
    if record.job_type == "recommendation_verification":
        verification = _get(
            db,
            RecommendationVerification,
            payload.get("verification_id"),
            "verificatie",
        )
        if not queue_has_capacity(VERIFICATION_QUEUE):
            return False
        task = db.get(RecommendationTask, verification.task_id)
        verification.status = "queued"
        verification.error_message = None
        verification.finished_at = None
        if task:
            task.verification_status = "queued"
        db.commit()
        queued = enqueue_recommendation_verification(
            str(verification.id),
            website_id=str(record.website_id) if record.website_id else None,
            priority=int(payload.get("priority", 50)),
        )
        if not queued:
            verification.status = "error"
            verification.error_message = "De verificatiewachtrij is tijdelijk vol."
            if task:
                task.verification_status = "error"
            db.commit()
        return queued
    raise DeadLetterError(f"Taaktype {record.job_type!r} kan niet automatisch worden hersteld.")


def _get(db: Session, model: type, raw_id: object, label: str):  # type: ignore[no-untyped-def]
    try:
        item_id = UUID(str(raw_id))
    except (TypeError, ValueError) as exc:
        raise DeadLetterError(f"De {label}-ID ontbreekt of is ongeldig.") from exc
    item = db.get(model, item_id)
    if item is None:
        raise DeadLetterError(f"De gekoppelde {label} bestaat niet meer.")
    return item

from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.queue import enqueue_crawl_job
from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.models.system import QueueDeadLetter
from app.schemas.system import QueueDeadLetterRead, QueueDeadLetterResolution
from app.services.authorization import require_global_role
from app.services.crawl_deployment import (
    deployment_drain_status,
    finish_deployment_drain,
    start_deployment_drain,
)
from app.services.dead_letters import DeadLetterError, requeue_dead_letter, resolve_dead_letter
from app.services.system_status import build_queue_status

router = APIRouter(tags=["system"])
logger = structlog.get_logger()


def _dead_letter_or_404(dead_letter_id: UUID, db: Session) -> QueueDeadLetter:
    record = db.get(QueueDeadLetter, dead_letter_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dead letter not found")
    return record


@router.get("/system/dead-letters", response_model=list[QueueDeadLetterRead])
def list_dead_letters(
    status: str | None = Query(default="unresolved"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> list[QueueDeadLetter]:
    require_global_role(principal, "superuser")
    query = select(QueueDeadLetter).order_by(QueueDeadLetter.failed_at.desc()).limit(limit)
    if status:
        query = query.where(QueueDeadLetter.status == status)
    return list(db.scalars(query))


@router.post("/system/dead-letters/{dead_letter_id}/requeue", response_model=QueueDeadLetterRead)
def requeue_failed_job(
    dead_letter_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> QueueDeadLetter:
    require_global_role(principal, "superuser")
    record = _dead_letter_or_404(dead_letter_id, db)
    try:
        requeue_dead_letter(db, record)
    except DeadLetterError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.refresh(record)
    return record


@router.post("/system/dead-letters/{dead_letter_id}/resolve", response_model=QueueDeadLetterRead)
def resolve_failed_job(
    dead_letter_id: UUID,
    payload: QueueDeadLetterResolution,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> QueueDeadLetter:
    require_global_role(principal, "superuser")
    record = _dead_letter_or_404(dead_letter_id, db)
    try:
        resolve_dead_letter(db, record, payload.resolution)
    except DeadLetterError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.refresh(record)
    return record


def _drain_payload(status) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {
        "active": status.active,
        "safe": status.safe,
        "tracked_jobs": len(status.tracked_job_ids),
        "waiting_jobs": len(status.waiting_job_ids),
    }


@router.get("/system/crawl-deployment")
def crawl_deployment_status(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    require_global_role(principal, "superuser")
    return _drain_payload(deployment_drain_status(db))


@router.post("/system/crawl-deployment/pause")
def pause_crawls_for_deployment(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    require_global_role(principal, "superuser")
    return _drain_payload(start_deployment_drain(db))


@router.post("/system/crawl-deployment/resume")
def resume_crawls_after_deployment(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    require_global_role(principal, "superuser")
    try:
        resumed = finish_deployment_drain(db)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if get_settings().app_env != "test":
        for job_id, job_type, attempt in resumed:
            enqueue_crawl_job(job_id, job_type=job_type, attempt=attempt)
    return {"active": False, "resumed_jobs": len(resumed)}


@router.get("/system/status")
def system_status(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, Any]:
    require_global_role(principal, "superuser", "admin", "user")
    database_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        database_status = "unavailable"

    try:
        queue_status = build_queue_status()
    except Exception:  # Redis/RQ failures must be reported, not break this endpoint.
        logger.warning("system_queue_status_unavailable", exc_info=True)
        queue_status = {
            "redis": "unavailable",
            "queues": {
                "crawls": {"status": "unavailable", "workers": 0, "queued_jobs": 0},
                "crawls_light": {
                    "status": "unavailable",
                    "workers": 0,
                    "queued_jobs": 0,
                },
                "crawls_full": {
                    "status": "unavailable",
                    "workers": 0,
                    "queued_jobs": 0,
                },
                "sitemaps": {
                    "status": "unavailable",
                    "workers": 0,
                    "queued_jobs": 0,
                },
                "verifications": {
                    "status": "unavailable",
                    "workers": 0,
                    "queued_jobs": 0,
                },
                "integrations": {
                    "status": "unavailable",
                    "workers": 0,
                    "queued_jobs": 0,
                },
                "maintenance": {
                    "status": "unavailable",
                    "workers": 0,
                    "queued_jobs": 0,
                },
                "exports": {"status": "unavailable", "workers": 0, "queued_jobs": 0},
            },
        }
    dead_letter_rows = (
        db.execute(
            select(QueueDeadLetter.queue_name, func.count(QueueDeadLetter.id))
            .where(QueueDeadLetter.status == "unresolved")
            .group_by(QueueDeadLetter.queue_name)
        ).all()
        if database_status == "ok"
        else []
    )
    dead_letters = {queue_name: int(count) for queue_name, count in dead_letter_rows}
    unresolved_dead_letters = sum(dead_letters.values())
    healthy = database_status == "ok" and unresolved_dead_letters == 0 and all(
        queue["status"] == "ok" for queue in queue_status["queues"].values()
    )
    return {
        "status": "ok" if healthy else "degraded",
        "api": "ok",
        "database": database_status,
        "dead_letters": {
            "unresolved": unresolved_dead_letters,
            "by_queue": dead_letters,
        },
        **queue_status,
    }

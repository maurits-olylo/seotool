from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.queue import enqueue_crawl_job
from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.services.authorization import require_global_role
from app.services.crawl_deployment import (
    deployment_drain_status,
    finish_deployment_drain,
    start_deployment_drain,
)
from app.services.system_status import build_queue_status

router = APIRouter(tags=["system"])
logger = structlog.get_logger()


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
        for job_id, attempt in resumed:
            enqueue_crawl_job(job_id, attempt=attempt)
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
                "default": {"status": "unavailable", "workers": 0, "queued_jobs": 0},
                "exports": {"status": "unavailable", "workers": 0, "queued_jobs": 0},
            },
        }
    healthy = database_status == "ok" and all(
        queue["status"] == "ok" for queue in queue_status["queues"].values()
    )
    return {
        "status": "ok" if healthy else "degraded",
        "api": "ok",
        "database": database_status,
        **queue_status,
    }

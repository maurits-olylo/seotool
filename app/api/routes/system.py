from typing import Any

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.services.authorization import require_global_role
from app.services.system_status import build_queue_status

router = APIRouter(tags=["system"])
logger = structlog.get_logger()


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

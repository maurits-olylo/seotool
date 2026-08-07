from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.models.opportunities import OpportunityEvaluation
from app.schemas.opportunities import OpportunityEvaluationRead
from app.services.authorization import require_website_access, require_website_write_access
from app.services.opportunity_engine import evaluate_website_opportunities

router = APIRouter(prefix="/websites/{website_id}/opportunity-evaluations", tags=["opportunities"])


@router.post("/evaluate")
def evaluate_opportunities(
    website_id: UUID,
    period_start: date,
    period_end: date,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, int]:
    require_website_write_access(db, principal, website_id)
    if period_start > period_end:
        raise HTTPException(status_code=422, detail="Start date must not be after end date")
    try:
        return evaluate_website_opportunities(db, website_id, period_start, period_end)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=list[OpportunityEvaluationRead])
def list_opportunity_evaluations(
    website_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> list[OpportunityEvaluation]:
    require_website_access(db, principal, website_id)
    return list(
        db.scalars(
            select(OpportunityEvaluation)
            .where(OpportunityEvaluation.website_id == website_id)
            .order_by(OpportunityEvaluation.created_at.desc())
            .limit(limit)
        )
    )

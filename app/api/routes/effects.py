from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.models.effects import EffectEvaluation
from app.schemas.effects import EffectEvaluationRead
from app.services.authorization import require_website_access, require_website_write_access
from app.services.effect_analysis import evaluate_effect_cohort

router = APIRouter(prefix="/websites/{website_id}/effect-evaluations", tags=["effects"])


@router.post("/evaluate", response_model=EffectEvaluationRead)
def evaluate_effects(
    website_id: UUID,
    change_period_start: date,
    change_period_end: date,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> EffectEvaluation:
    require_website_write_access(db, principal, website_id)
    try:
        evaluation = evaluate_effect_cohort(db, website_id, change_period_start, change_period_end)
        db.commit()
        db.refresh(evaluation)
        return evaluation
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=list[EffectEvaluationRead])
def list_effect_evaluations(
    website_id: UUID,
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> list[EffectEvaluation]:
    require_website_access(db, principal, website_id)
    return list(
        db.scalars(
            select(EffectEvaluation)
            .where(EffectEvaluation.website_id == website_id)
            .order_by(EffectEvaluation.created_at.desc())
            .limit(limit)
        )
    )

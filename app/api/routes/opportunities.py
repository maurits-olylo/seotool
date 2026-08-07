from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.models.opportunities import OpportunityEvaluation
from app.schemas.opportunities import OpportunityEvaluationRead
from app.services.authorization import require_website_access

router = APIRouter(prefix="/websites/{website_id}/opportunity-evaluations", tags=["opportunities"])


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

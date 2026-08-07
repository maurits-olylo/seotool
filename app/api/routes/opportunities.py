from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.models.discovery import Url
from app.models.opportunities import OpportunityEvaluation
from app.schemas.opportunities import OpportunityEvaluationRead
from app.schemas.recommendations import RecommendationTaskRead
from app.services.authorization import require_website_access, require_website_write_access
from app.services.opportunity_engine import evaluate_website_opportunities
from app.services.opportunity_tasks import OpportunityTaskError, create_task_from_opportunity

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
    latest_only: bool = False,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> list[dict[str, object]]:
    require_website_access(db, principal, website_id)
    evaluations = list(
        db.scalars(
            select(OpportunityEvaluation)
            .where(OpportunityEvaluation.website_id == website_id)
            .order_by(
                OpportunityEvaluation.period_end.desc(), OpportunityEvaluation.created_at.desc()
            )
            .limit(limit)
        )
    )
    url_ids = {item.primary_url_id for item in evaluations if item.primary_url_id}
    urls = (
        dict(db.execute(select(Url.id, Url.normalized_url).where(Url.id.in_(url_ids))).all())
        if url_ids
        else {}
    )
    previous_by_id: dict[UUID, float | None] = {}
    latest_by_scope: dict[tuple[str, str, str], float | None] = {}
    for item in reversed(evaluations):
        key = (item.scope_type, item.scope_key, item.formula_version)
        previous_by_id[item.id] = latest_by_scope.get(key)
        latest_by_scope[key] = item.total_score
    result = []
    returned_scopes: set[tuple[str, str, str]] = set()
    for item in evaluations:
        scope = (item.scope_type, item.scope_key, item.formula_version)
        if latest_only and scope in returned_scopes:
            continue
        returned_scopes.add(scope)
        previous = previous_by_id[item.id]
        payload = OpportunityEvaluationRead.model_validate(item).model_dump()
        payload["primary_url"] = urls.get(item.primary_url_id)
        payload["previous_total_score"] = previous
        payload["total_score_change"] = (
            round(item.total_score - previous, 1)
            if item.total_score is not None and previous is not None
            else None
        )
        result.append(payload)
    return result


@router.post("/{evaluation_id}/task", response_model=RecommendationTaskRead, status_code=201)
def promote_opportunity_to_task(
    website_id: UUID,
    evaluation_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> RecommendationTaskRead:
    require_website_write_access(db, principal, website_id)
    evaluation = db.get(OpportunityEvaluation, evaluation_id)
    if evaluation is None or evaluation.website_id != website_id:
        raise HTTPException(status_code=404, detail="Opportunity evaluation not found")
    try:
        task, _ = create_task_from_opportunity(db, evaluation=evaluation, principal=principal)
    except OpportunityTaskError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RecommendationTaskRead.model_validate(task)

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.models.discovery import Url
from app.models.issues import Issue
from app.models.recommendations import (
    RecommendationFeedback,
    RecommendationTask,
    RecommendationTaskEvent,
    RecommendationTaskIssue,
    RecommendationTaskUrl,
    RecommendationVerification,
)
from app.schemas.recommendations import (
    RecommendationDefinitionRead,
    RecommendationFeedbackCreate,
    RecommendationFeedbackRead,
    RecommendationTaskDetailRead,
    RecommendationTaskRead,
    RecommendationTaskUpdate,
    RecommendationTaskUrlCreate,
    RecommendationTaskUrlRead,
    RecommendationVerificationPlanRead,
    RecommendationVerificationRead,
)
from app.services.authorization import require_website_access, require_write_access
from app.services.recommendation_library import DEFINITIONS
from app.services.recommendation_tasks import (
    RecommendationTaskError,
    add_task_url,
    create_task_from_issue,
    record_feedback,
    remove_task_url,
    update_task,
    verification_scope_plan,
)
from app.services.recommendation_verifications import request_verification

router = APIRouter(tags=["recommendations"])


@router.get("/recommendation-types", response_model=list[RecommendationDefinitionRead])
def list_recommendation_types() -> tuple[object, ...]:
    return DEFINITIONS


@router.post(
    "/issues/{issue_id}/recommendation-task",
    response_model=RecommendationTaskRead,
    status_code=status.HTTP_201_CREATED,
)
def create_recommendation_task(
    issue_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> RecommendationTask:
    require_write_access(principal)
    issue = db.get(Issue, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    require_website_access(db, principal, issue.website_id)
    try:
        return create_task_from_issue(db, issue=issue, principal=principal)
    except RecommendationTaskError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/websites/{website_id}/recommendation-tasks",
    response_model=list[RecommendationTaskRead],
)
def list_recommendation_tasks(
    website_id: UUID,
    task_status: str = Query(default="active", alias="status"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> list[RecommendationTask]:
    require_website_access(db, principal, website_id)
    query = (
        select(RecommendationTask)
        .where(RecommendationTask.website_id == website_id)
        .order_by(RecommendationTask.updated_at.desc())
    )
    if task_status == "active":
        query = query.where(RecommendationTask.status != "closed")
    elif task_status != "all":
        query = query.where(RecommendationTask.status == task_status)
    return list(db.scalars(query))


@router.get(
    "/recommendation-tasks/{task_id}",
    response_model=RecommendationTaskDetailRead,
)
def get_recommendation_task(
    task_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    task = _task_or_404(db, task_id)
    require_website_access(db, principal, task.website_id)
    issue_ids = list(
        db.scalars(
            select(RecommendationTaskIssue.issue_id).where(
                RecommendationTaskIssue.task_id == task.id
            )
        )
    )
    url_rows = list(
        db.execute(
            select(RecommendationTaskUrl, Url.normalized_url)
            .join(Url, Url.id == RecommendationTaskUrl.url_id)
            .where(RecommendationTaskUrl.task_id == task.id)
            .order_by(RecommendationTaskUrl.created_at)
        )
    )
    events = list(
        db.scalars(
            select(RecommendationTaskEvent)
            .where(RecommendationTaskEvent.task_id == task.id)
            .order_by(RecommendationTaskEvent.occurred_at)
        )
    )
    return {
        **RecommendationTaskRead.model_validate(task).model_dump(),
        "issue_ids": issue_ids,
        "urls": [
            {
                "id": task_url.id,
                "url_id": task_url.url_id,
                "role": task_url.role,
                "is_user_supplied": task_url.is_user_supplied,
                "url": normalized_url,
            }
            for task_url, normalized_url in url_rows
        ],
        "events": events,
    }


@router.post(
    "/recommendation-tasks/{task_id}/urls",
    response_model=RecommendationTaskUrlRead,
    status_code=status.HTTP_201_CREATED,
)
def create_recommendation_task_url(
    task_id: UUID,
    payload: RecommendationTaskUrlCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> RecommendationTaskUrl:
    require_write_access(principal)
    task = _task_or_404(db, task_id)
    require_website_access(db, principal, task.website_id)
    try:
        return add_task_url(
            db,
            task=task,
            role=payload.role,
            raw_url=payload.url,
            principal=principal,
        )
    except RecommendationTaskError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete(
    "/recommendation-tasks/{task_id}/urls/{task_url_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_recommendation_task_url(
    task_id: UUID,
    task_url_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> None:
    require_write_access(principal)
    task = _task_or_404(db, task_id)
    require_website_access(db, principal, task.website_id)
    task_url = db.get(RecommendationTaskUrl, task_url_id)
    if not task_url or task_url.task_id != task.id:
        raise HTTPException(status_code=404, detail="Task URL not found")
    remove_task_url(db, task=task, task_url=task_url, principal=principal)


@router.patch(
    "/recommendation-tasks/{task_id}",
    response_model=RecommendationTaskRead,
)
def patch_recommendation_task(
    task_id: UUID,
    payload: RecommendationTaskUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> RecommendationTask:
    require_write_access(principal)
    task = _task_or_404(db, task_id)
    require_website_access(db, principal, task.website_id)
    try:
        return update_task(db, task=task, payload=payload, principal=principal)
    except RecommendationTaskError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/recommendation-tasks/{task_id}/feedback",
    response_model=list[RecommendationFeedbackRead],
)
def list_recommendation_feedback(
    task_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> list[RecommendationFeedback]:
    task = _task_or_404(db, task_id)
    require_website_access(db, principal, task.website_id)
    return list(
        db.scalars(
            select(RecommendationFeedback)
            .where(RecommendationFeedback.task_id == task.id)
            .order_by(RecommendationFeedback.created_at.desc())
        )
    )


@router.post(
    "/recommendation-tasks/{task_id}/feedback",
    response_model=RecommendationFeedbackRead,
    status_code=status.HTTP_201_CREATED,
)
def create_recommendation_feedback(
    task_id: UUID,
    payload: RecommendationFeedbackCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> RecommendationFeedback:
    require_write_access(principal)
    task = _task_or_404(db, task_id)
    require_website_access(db, principal, task.website_id)
    try:
        return record_feedback(db, task=task, payload=payload, principal=principal)
    except RecommendationTaskError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/recommendation-tasks/{task_id}/verification-plan",
    response_model=RecommendationVerificationPlanRead,
)
def get_recommendation_verification_plan(
    task_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    task = _task_or_404(db, task_id)
    require_website_access(db, principal, task.website_id)
    return verification_scope_plan(db, task=task)


@router.get(
    "/recommendation-tasks/{task_id}/verifications",
    response_model=list[RecommendationVerificationRead],
)
def list_recommendation_verifications(
    task_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> list[RecommendationVerification]:
    task = _task_or_404(db, task_id)
    require_website_access(db, principal, task.website_id)
    return list(
        db.scalars(
            select(RecommendationVerification)
            .where(RecommendationVerification.task_id == task.id)
            .order_by(RecommendationVerification.created_at.desc())
        )
    )


@router.post(
    "/recommendation-tasks/{task_id}/verifications",
    response_model=RecommendationVerificationRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_recommendation_verification(
    task_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> RecommendationVerification:
    require_write_access(principal)
    task = _task_or_404(db, task_id)
    require_website_access(db, principal, task.website_id)
    try:
        return request_verification(db, task=task, principal=principal)
    except RecommendationTaskError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _task_or_404(db: Session, task_id: UUID) -> RecommendationTask:
    task = db.get(RecommendationTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Recommendation task not found")
    return task

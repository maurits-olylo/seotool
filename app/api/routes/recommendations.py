from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
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
    TaskNotification,
    TaskNotificationReceipt,
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
    TaskNotificationRead,
)
from app.services.authorization import require_website_access, require_website_write_access
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
    issue = db.get(Issue, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    require_website_write_access(db, principal, issue.website_id)
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
    primary_role: str | None = None,
    priority: str | None = Query(default=None, pattern="^(critical|high|normal|low)$"),
    assigned_to_user_id: UUID | None = None,
    unassigned: bool = False,
    verification_status: str | None = None,
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
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
    if primary_role is not None:
        query = query.where(RecommendationTask.primary_role == primary_role)
    if priority is not None:
        query = query.where(RecommendationTask.priority == priority)
    if unassigned:
        query = query.where(RecommendationTask.assigned_to_user_id.is_(None))
    elif assigned_to_user_id is not None:
        query = query.where(RecommendationTask.assigned_to_user_id == assigned_to_user_id)
    if verification_status is not None:
        query = query.where(RecommendationTask.verification_status == verification_status)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(
            or_(
                RecommendationTask.title.ilike(pattern),
                RecommendationTask.action.ilike(pattern),
            )
        )
    return list(db.scalars(query.offset(offset).limit(limit)))


@router.get(
    "/websites/{website_id}/task-notifications",
    response_model=list[TaskNotificationRead],
)
def list_task_notifications(
    website_id: UUID,
    unread_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> list[dict[str, object]]:
    require_website_access(db, principal, website_id)
    query = (
        select(TaskNotification, TaskNotificationReceipt.read_at)
        .outerjoin(
            TaskNotificationReceipt,
            (TaskNotificationReceipt.notification_id == TaskNotification.id)
            & (TaskNotificationReceipt.user_id == principal.user_id),
        )
        .where(TaskNotification.website_id == website_id)
        .order_by(TaskNotification.created_at.desc())
        .limit(limit)
    )
    if unread_only and principal.user_id is not None:
        query = query.where(TaskNotificationReceipt.notification_id.is_(None))
    return [
        {**TaskNotificationRead.model_validate(notification).model_dump(), "read_at": read_at}
        for notification, read_at in db.execute(query)
    ]


@router.post("/task-notifications/{notification_id}/read", status_code=204)
def mark_task_notification_read(
    notification_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> None:
    if principal.user_id is None:
        raise HTTPException(status_code=403, detail="Een gebruikerssessie is vereist")
    notification = db.get(TaskNotification, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="Melding niet gevonden")
    require_website_access(db, principal, notification.website_id)
    receipt = db.get(TaskNotificationReceipt, (notification.id, principal.user_id))
    if receipt is None:
        db.add(
            TaskNotificationReceipt(
                notification_id=notification.id,
                user_id=principal.user_id,
            )
        )
        db.commit()


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
    task = _task_or_404(db, task_id)
    require_website_write_access(db, principal, task.website_id)
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
    task = _task_or_404(db, task_id)
    require_website_write_access(db, principal, task.website_id)
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
    task = _task_or_404(db, task_id)
    require_website_write_access(db, principal, task.website_id)
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
    task = _task_or_404(db, task_id)
    require_website_write_access(db, principal, task.website_id)
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
    task = _task_or_404(db, task_id)
    require_website_write_access(db, principal, task.website_id)
    try:
        return request_verification(db, task=task, principal=principal)
    except RecommendationTaskError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _task_or_404(db: Session, task_id: UUID) -> RecommendationTask:
    task = db.get(RecommendationTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Recommendation task not found")
    return task

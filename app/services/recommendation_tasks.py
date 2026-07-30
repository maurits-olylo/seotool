from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal
from app.models.common import utc_now
from app.models.issues import ActivityLog, Issue
from app.models.recommendations import (
    RecommendationFeedback,
    RecommendationTask,
    RecommendationTaskEvent,
    RecommendationTaskIssue,
    RecommendationTaskUrl,
)
from app.models.user import ClientMembership, User
from app.models.website import Website
from app.schemas.recommendations import RecommendationFeedbackCreate, RecommendationTaskUpdate
from app.services.recommendation_library import recommendation_for_issue_type

ACTIVE_TASK_STATUSES = {"open", "planned", "in_progress", "waiting_for_input", "implemented"}
ALLOWED_TRANSITIONS = {
    "open": {"planned", "in_progress", "closed"},
    "planned": {"in_progress", "waiting_for_input", "closed"},
    "in_progress": {"waiting_for_input", "implemented", "closed"},
    "waiting_for_input": {"planned", "in_progress", "closed"},
    "implemented": {"in_progress", "closed"},
    "closed": {"open"},
}
PRIORITY_RANK = {"low": 0, "normal": 1, "high": 2, "critical": 3}
SEVERITY_PRIORITY = {"low": "low", "medium": "normal", "high": "high"}


class RecommendationTaskError(ValueError):
    pass


def actor_label(db: Session, principal: Principal) -> str:
    actor = db.get(User, principal.user_id) if principal.user_id else None
    return actor.email if actor else "API"


def create_task_from_issue(
    db: Session, *, issue: Issue, principal: Principal
) -> RecommendationTask:
    definition = recommendation_for_issue_type(issue.issue_type)
    if definition is None:
        raise RecommendationTaskError(
            f"Voor issuetype {issue.issue_type} bestaat nog geen taakdefinitie."
        )
    existing = db.scalar(
        select(RecommendationTask)
        .join(
            RecommendationTaskIssue,
            RecommendationTaskIssue.task_id == RecommendationTask.id,
        )
        .where(
            RecommendationTaskIssue.issue_id == issue.id,
            RecommendationTask.recommendation_type == definition.key,
            RecommendationTask.status.in_(ACTIVE_TASK_STATUSES),
        )
        .limit(1)
    )
    if existing:
        raise RecommendationTaskError("Voor dit issue bestaat al een actieve taak.")

    priority = _strongest_priority(
        definition.default_priority,
        SEVERITY_PRIORITY.get(issue.severity, "normal"),
    )
    task = RecommendationTask(
        website_id=issue.website_id,
        created_by_user_id=principal.user_id,
        primary_issue_id=issue.id,
        recommendation_type=definition.key,
        definition_version=definition.version,
        title=definition.title,
        category=issue.category,
        primary_role=definition.primary_role,
        supporting_roles=list(definition.supporting_roles),
        priority=priority,
        priority_reason=(
            f"Standaardprioriteit {definition.default_priority}; het bronsignaal heeft "
            f"ernst {issue.severity} en confidence {issue.confidence}."
        ),
        effort_min_minutes=definition.effort_minutes[0] if definition.effort_minutes else None,
        effort_max_minutes=definition.effort_minutes[1] if definition.effort_minutes else None,
        effort_confidence="medium" if definition.effort_minutes else "low",
        feasibility=definition.feasibility,
        action=issue.recommended_action,
        rationale=issue.description,
        steps=list(definition.steps),
        acceptance_criteria=list(definition.completion_criteria),
        verification_spec={"scope": list(definition.verification_scope)},
    )
    db.add(task)
    db.flush()
    db.add(RecommendationTaskIssue(task_id=task.id, issue_id=issue.id))
    if issue.url_id:
        db.add(
            RecommendationTaskUrl(
                task_id=task.id,
                url_id=issue.url_id,
                role=_primary_url_role(definition.verification_scope),
            )
        )
    label = actor_label(db, principal)
    db.add_all(
        [
            RecommendationTaskEvent(
                task_id=task.id,
                actor_user_id=principal.user_id,
                actor_label=label,
                event_type="created",
                new_status=task.status,
                details={
                    "issue_id": str(issue.id),
                    "definition_version": definition.version,
                },
            ),
            ActivityLog(
                website_id=issue.website_id,
                actor=label,
                activity_type="recommendation_task_created",
                summary=f"Taak aangemaakt: {task.title}",
                details={"task_id": str(task.id), "issue_id": str(issue.id)},
            ),
        ]
    )
    db.commit()
    db.refresh(task)
    return task


def update_task(
    db: Session,
    *,
    task: RecommendationTask,
    payload: RecommendationTaskUpdate,
    principal: Principal,
) -> RecommendationTask:
    values = payload.model_dump(exclude_unset=True, exclude={"comment"})
    new_status = values.get("status")
    previous_status = task.status
    if new_status and new_status != previous_status:
        if new_status not in ALLOWED_TRANSITIONS[previous_status]:
            raise RecommendationTaskError(
                f"Statusovergang {previous_status} → {new_status} is niet toegestaan."
            )
        if previous_status == "closed" and not payload.comment:
            raise RecommendationTaskError("Heropenen vereist een toelichting.")
    _validate_assignee(db, task.website_id, values.get("assigned_to_user_id"))
    effective_min = values.get("effort_min_minutes", task.effort_min_minutes)
    effective_max = values.get("effort_max_minutes", task.effort_max_minutes)
    if effective_min is not None and effective_max is not None and effective_max < effective_min:
        raise RecommendationTaskError("De maximale tijd moet gelijk zijn aan of boven het minimum.")

    if new_status == "closed":
        task.closed_at = utc_now()
    elif new_status and previous_status == "closed":
        task.closed_at = None
        values["close_reason"] = None
    if new_status == "implemented" and not task.implemented_at:
        task.implemented_at = utc_now()
    for key, value in values.items():
        setattr(task, key, value)

    label = actor_label(db, principal)
    event_type = "status_changed" if new_status and new_status != previous_status else "updated"
    db.add(
        RecommendationTaskEvent(
            task_id=task.id,
            actor_user_id=principal.user_id,
            actor_label=label,
            event_type=event_type,
            previous_status=previous_status if event_type == "status_changed" else None,
            new_status=task.status if event_type == "status_changed" else None,
            comment=payload.comment,
            details={key: _json_value(value) for key, value in values.items()},
        )
    )
    if event_type == "status_changed":
        db.add(
            ActivityLog(
                website_id=task.website_id,
                actor=label,
                activity_type="recommendation_task_status_changed",
                summary=f"{task.title}: {previous_status} → {task.status}",
                details={
                    "task_id": str(task.id),
                    "from": previous_status,
                    "to": task.status,
                },
            )
        )
    db.commit()
    db.refresh(task)
    return task


def record_feedback(
    db: Session,
    *,
    task: RecommendationTask,
    payload: RecommendationFeedbackCreate,
    principal: Principal,
) -> RecommendationFeedback:
    if task.status not in {"implemented", "closed"}:
        raise RecommendationTaskError(
            "Feedback kan pas worden vastgelegd nadat de taak is uitgevoerd of afgesloten."
        )
    values = payload.model_dump()
    if values["actual_minutes"] is not None and values["actual_effort_band"] is None:
        values["actual_effort_band"] = _effort_band(values["actual_minutes"])
    feedback = RecommendationFeedback(
        task_id=task.id,
        actor_user_id=principal.user_id,
        **values,
    )
    db.add(feedback)
    db.flush()
    label = actor_label(db, principal)
    structured_details = {
        key: value
        for key, value in values.items()
        if key != "notes" and value is not None
    }
    db.add_all(
        [
            RecommendationTaskEvent(
                task_id=task.id,
                actor_user_id=principal.user_id,
                actor_label=label,
                event_type="feedback_recorded",
                details=structured_details,
            ),
            ActivityLog(
                website_id=task.website_id,
                actor=label,
                activity_type="recommendation_feedback_recorded",
                summary=f"Uitvoeringsfeedback vastgelegd: {task.title}",
                details={"task_id": str(task.id), **structured_details},
            ),
        ]
    )
    db.commit()
    db.refresh(feedback)
    return feedback


def _strongest_priority(first: str, second: str) -> str:
    return first if PRIORITY_RANK[first] >= PRIORITY_RANK[second] else second


def _primary_url_role(scope: tuple[str, ...]) -> str:
    return scope[0] if scope else "changed"


def _validate_assignee(db: Session, website_id: UUID, user_id: UUID | None) -> None:
    if user_id is None:
        return
    user = db.get(User, user_id)
    website = db.get(Website, website_id)
    if not user or not user.is_active or not website:
        raise RecommendationTaskError("De gekozen eigenaar is niet beschikbaar.")
    if user.role == "superuser":
        return
    membership = db.scalar(
        select(ClientMembership.id).where(
            ClientMembership.user_id == user.id,
            ClientMembership.client_id == website.client_id,
        )
    )
    if not membership:
        raise RecommendationTaskError("De gekozen eigenaar heeft geen toegang tot deze klant.")


def _json_value(value: object) -> object:
    return str(value) if isinstance(value, UUID) else value


def _effort_band(minutes: int) -> str:
    if minutes < 15:
        return "under_15"
    if minutes <= 30:
        return "15_30"
    if minutes <= 60:
        return "30_60"
    if minutes <= 120:
        return "1_2_hours"
    if minutes <= 240:
        return "2_4_hours"
    if minutes <= 480:
        return "4_8_hours"
    return "more_than_day"

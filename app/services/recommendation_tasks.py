from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal
from app.models.common import utc_now
from app.models.crawl import UrlLink, UrlSnapshot
from app.models.discovery import Url
from app.models.issues import ActivityLog, Issue, IssueOccurrence
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
from app.services.recommendation_library import (
    get_recommendation_definition,
    recommendation_for_issue_type,
)
from app.services.task_notifications import add_task_notification
from app.services.url_normalization import InvalidUrlError, normalize_url
from app.services.url_registry import register_url
from app.services.url_scope import is_url_in_website_scope

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
SCOPED_VERIFICATION_TYPES = {
    "repair_broken_internal_link",
    "replace_redirected_internal_link",
    "restore_or_redirect_missing_page",
    "fix_redirect_chain_or_loop",
    "correct_indexability",
    "correct_canonical",
    "add_or_correct_title",
    "add_primary_heading",
    "add_meta_description",
    "repair_structured_data",
}
VERIFICATION_URL_ROLES = {
    "repair_broken_internal_link": {"source", "broken_target", "replacement_target"},
    "replace_redirected_internal_link": {"source", "target", "expected_target"},
    "restore_or_redirect_missing_page": {"old", "new"},
    "fix_redirect_chain_or_loop": {"source", "expected_target"},
    "correct_indexability": {"changed"},
    "correct_canonical": {"source", "expected_canonical"},
    "add_or_correct_title": {"changed", "sample"},
    "add_primary_heading": {"changed", "sample"},
    "add_meta_description": {"changed", "sample"},
    "repair_structured_data": {"changed", "sample"},
}


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
        required_input=list(definition.required_input),
        acceptance_criteria=list(definition.completion_criteria),
        verification_spec={"scope": list(definition.verification_scope)},
    )
    db.add(task)
    db.flush()
    db.add(RecommendationTaskIssue(task_id=task.id, issue_id=issue.id))
    for url_id, role in _task_url_scope_from_issue(
        db,
        issue=issue,
        verification_type=definition.key,
        default_scope=definition.verification_scope,
    ):
        db.add(
            RecommendationTaskUrl(
                task_id=task.id,
                url_id=url_id,
                role=role,
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
    previous_assignee_id = task.assigned_to_user_id
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
        add_task_notification(
            db,
            task=task,
            notification_type="task_status_changed",
            title=f"Taakstatus gewijzigd: {task.title}",
            message=f"De taak ging van {previous_status} naar {task.status}.",
            details={"from": previous_status, "to": task.status},
        )
    if "assigned_to_user_id" in values and values["assigned_to_user_id"] != previous_assignee_id:
        add_task_notification(
            db,
            task=task,
            notification_type="task_assigned",
            title=f"Taak toegewezen: {task.title}",
            message="De uitvoerder van deze taak is gewijzigd.",
            details={
                "from": str(previous_assignee_id) if previous_assignee_id else None,
                "to": (
                    str(values["assigned_to_user_id"]) if values["assigned_to_user_id"] else None
                ),
            },
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
        key: value for key, value in values.items() if key != "notes" and value is not None
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


def verification_scope_plan(
    db: Session,
    *,
    task: RecommendationTask,
) -> dict[str, object]:
    task_urls = list(
        db.scalars(select(RecommendationTaskUrl).where(RecommendationTaskUrl.task_id == task.id))
    )
    present_roles = sorted({item.role for item in task_urls})
    supported = task.recommendation_type in SCOPED_VERIFICATION_TYPES
    if not supported:
        return {
            "task_id": task.id,
            "verification_type": task.recommendation_type,
            "scope_version": task.definition_version,
            "supported": False,
            "required_roles": [],
            "present_roles": present_roles,
            "missing_roles": [],
            "url_count": len(task_urls),
            "can_request": False,
            "blocking_reason": (
                "Voor dit aanbevelingstype is nog geen verificatieregel beschikbaar."
            ),
        }
    definition = get_recommendation_definition(task.recommendation_type)
    required_roles = list(definition.verification_scope)
    missing_roles = [role for role in required_roles if role not in present_roles]
    blocking_reason: str | None = None
    if task.status != "implemented":
        blocking_reason = "De taak moet eerst als uitgevoerd zijn gemarkeerd."
    elif missing_roles:
        blocking_reason = "De verificatiescope mist URL-rollen: " + ", ".join(missing_roles) + "."
    return {
        "task_id": task.id,
        "verification_type": task.recommendation_type,
        "scope_version": definition.version,
        "supported": True,
        "required_roles": required_roles,
        "present_roles": present_roles,
        "missing_roles": missing_roles,
        "url_count": len(task_urls),
        "can_request": blocking_reason is None,
        "blocking_reason": blocking_reason,
    }


def add_task_url(
    db: Session,
    *,
    task: RecommendationTask,
    role: str,
    raw_url: str,
    principal: Principal,
) -> RecommendationTaskUrl:
    allowed_roles = VERIFICATION_URL_ROLES.get(task.recommendation_type, set())
    if role not in allowed_roles:
        raise RecommendationTaskError(
            f"URL-rol {role} is niet toegestaan voor dit aanbevelingstype."
        )
    website = db.get(Website, task.website_id)
    if website is None:
        raise RecommendationTaskError("De website bestaat niet meer.")
    try:
        normalized = normalize_url(raw_url)
    except InvalidUrlError as exc:
        raise RecommendationTaskError(str(exc)) from exc
    settings = website.settings
    if not is_url_in_website_scope(
        normalized,
        base_url=website.base_url,
        allowed_subdomains=settings.allowed_subdomains if settings else [],
    ):
        raise RecommendationTaskError("De URL valt buiten de toegestane websitescope.")
    url = register_url(
        db,
        website_id=website.id,
        raw_url=normalized,
        source_type="manual",
        source_url=f"recommendation_task:{task.id}",
        ignored_query_parameters=frozenset(settings.ignored_query_parameters if settings else []),
    )
    existing = db.scalar(
        select(RecommendationTaskUrl).where(
            RecommendationTaskUrl.task_id == task.id,
            RecommendationTaskUrl.url_id == url.id,
            RecommendationTaskUrl.role == role,
        )
    )
    if existing:
        raise RecommendationTaskError("Deze URL staat al met dezelfde rol in de taak.")
    task_url = RecommendationTaskUrl(
        task_id=task.id,
        url_id=url.id,
        role=role,
        is_user_supplied=True,
    )
    db.add(task_url)
    db.flush()
    _record_scope_event(
        db,
        task=task,
        principal=principal,
        event_type="verification_scope_url_added",
        url=url,
        role=role,
    )
    db.commit()
    db.refresh(task_url)
    return task_url


def remove_task_url(
    db: Session,
    *,
    task: RecommendationTask,
    task_url: RecommendationTaskUrl,
    principal: Principal,
) -> None:
    url = db.get(Url, task_url.url_id)
    role = task_url.role
    db.delete(task_url)
    if url:
        _record_scope_event(
            db,
            task=task,
            principal=principal,
            event_type="verification_scope_url_removed",
            url=url,
            role=role,
        )
    db.commit()


def _record_scope_event(
    db: Session,
    *,
    task: RecommendationTask,
    principal: Principal,
    event_type: str,
    url: Url,
    role: str,
) -> None:
    label = actor_label(db, principal)
    details = {"url_id": str(url.id), "url": url.normalized_url, "role": role}
    db.add_all(
        [
            RecommendationTaskEvent(
                task_id=task.id,
                actor_user_id=principal.user_id,
                actor_label=label,
                event_type=event_type,
                details=details,
            ),
            ActivityLog(
                website_id=task.website_id,
                actor=label,
                activity_type=event_type,
                summary=f"Verificatiescope bijgewerkt: {task.title}",
                details={"task_id": str(task.id), **details},
            ),
        ]
    )


def _strongest_priority(first: str, second: str) -> str:
    return first if PRIORITY_RANK[first] >= PRIORITY_RANK[second] else second


def _primary_url_role(scope: tuple[str, ...]) -> str:
    return scope[0] if scope else "changed"


def _task_url_scope_from_issue(
    db: Session,
    *,
    issue: Issue,
    verification_type: str,
    default_scope: tuple[str, ...],
) -> list[tuple[UUID, str]]:
    occurrence = db.scalar(
        select(IssueOccurrence)
        .where(IssueOccurrence.issue_id == issue.id)
        .order_by(IssueOccurrence.detected_at.desc())
        .limit(1)
    )
    scope: list[tuple[UUID, str]] = []
    if verification_type in {
        "add_or_correct_title",
        "add_primary_heading",
        "add_meta_description",
        "repair_structured_data",
    }:
        if issue.url_id is not None:
            scope.append((issue.url_id, "changed"))
        evidence = occurrence.evidence if occurrence else {}
        related_urls = evidence.get("related_urls", [])
        if isinstance(related_urls, list):
            for value in related_urls:
                if isinstance(value, str):
                    sample = _existing_url(db, issue.website_id, value)
                    if sample:
                        scope.append((sample.id, "sample"))
        clusters = evidence.get("clusters", [])
        if isinstance(clusters, list):
            for cluster in clusters:
                if not isinstance(cluster, dict):
                    continue
                for value in cluster.get("urls", []):
                    if isinstance(value, str):
                        changed = _existing_url(db, issue.website_id, value)
                        if changed:
                            scope.append((changed.id, "changed"))
        return list(dict.fromkeys(scope))
    if issue.url_id is None:
        return []
    if verification_type == "repair_broken_internal_link":
        if issue.issue_type == "multiple_broken_internal_links":
            scope.append((issue.url_id, "source"))
            for item in occurrence.evidence.get("broken_links", []) if occurrence else []:
                if isinstance(item, dict) and isinstance(item.get("target_url"), str):
                    target = _existing_url(db, issue.website_id, item["target_url"])
                    if target:
                        scope.append((target.id, "broken_target"))
        else:
            scope.append((issue.url_id, "broken_target"))
            if occurrence:
                source_ids = db.scalars(
                    select(UrlLink.source_url_id)
                    .where(
                        UrlLink.crawl_run_id == occurrence.crawl_run_id,
                        UrlLink.target_url_id == issue.url_id,
                        UrlLink.source_url_id != issue.url_id,
                        UrlLink.is_internal.is_(True),
                    )
                    .distinct()
                )
                scope.extend((source_id, "source") for source_id in source_ids)
    elif verification_type == "replace_redirected_internal_link":
        scope.append((issue.url_id, "target"))
        evidence = occurrence.evidence if occurrence else {}
        for value in evidence.get("source_urls", []):
            if isinstance(value, str):
                source = _existing_url(db, issue.website_id, value)
                if source:
                    scope.append((source.id, "source"))
        final_url = evidence.get("final_url")
        if isinstance(final_url, str):
            target = _existing_url(db, issue.website_id, final_url)
            if target:
                scope.append((target.id, "expected_target"))
        if occurrence and not any(role == "source" for _url_id, role in scope):
            source_ids = db.scalars(
                select(UrlLink.source_url_id)
                .where(
                    UrlLink.crawl_run_id == occurrence.crawl_run_id,
                    UrlLink.target_url_id == issue.url_id,
                    UrlLink.source_url_id != issue.url_id,
                    UrlLink.is_internal.is_(True),
                )
                .distinct()
            )
            scope.extend((source_id, "source") for source_id in source_ids)
    elif verification_type == "restore_or_redirect_missing_page":
        scope.append((issue.url_id, "old"))
    elif verification_type == "fix_redirect_chain_or_loop":
        scope.append((issue.url_id, "source"))
        snapshot = (
            db.get(UrlSnapshot, occurrence.snapshot_id)
            if occurrence and occurrence.snapshot_id
            else None
        )
        if snapshot and snapshot.final_url and snapshot.final_url != snapshot.requested_url:
            target = _existing_url(db, issue.website_id, snapshot.final_url)
            if target:
                scope.append((target.id, "expected_target"))
    elif verification_type == "correct_canonical":
        scope.append((issue.url_id, "source"))
    elif verification_type == "correct_indexability":
        scope.append((issue.url_id, "changed"))
    else:
        scope.append((issue.url_id, _primary_url_role(default_scope)))
    return list(dict.fromkeys(scope))


def _existing_url(db: Session, website_id: UUID, value: str) -> Url | None:
    try:
        normalized = normalize_url(value)
    except InvalidUrlError:
        return None
    return db.scalar(
        select(Url).where(
            Url.website_id == website_id,
            Url.normalized_url == normalized,
        )
    )


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

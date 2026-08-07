from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal
from app.models.discovery import Url
from app.models.issues import ActivityLog, Issue
from app.models.opportunities import OpportunityEvaluation
from app.models.recommendations import (
    RecommendationTask,
    RecommendationTaskEvent,
    RecommendationTaskIssue,
    RecommendationTaskUrl,
)
from app.services.recommendation_tasks import ACTIVE_TASK_STATUSES, actor_label

PATTERN_LABELS = {
    "ctr": "Verbeter zoekresultaat voor een kansrijke pagina",
    "page_two": "Versterk een pagina op de tweede zoekresultatenpagina",
    "internal_link": "Versterk interne links naar een belangrijke pagina",
}
PRIORITIES = {"high_opportunity": "high", "opportunity": "normal", "monitor": "low"}


class OpportunityTaskError(ValueError):
    pass


def create_task_from_opportunity(
    db: Session, *, evaluation: OpportunityEvaluation, principal: Principal
) -> tuple[RecommendationTask, bool]:
    if evaluation.priority_class == "insufficient_evidence" or evaluation.total_score is None:
        raise OpportunityTaskError("Onvoldoende bewijs om van deze kans een taak te maken.")

    pattern = str(evaluation.source_coverage.get("pattern") or "optimization")
    recommendation_type = f"opportunity_{pattern}"
    for task in db.scalars(
        select(RecommendationTask).where(
            RecommendationTask.website_id == evaluation.website_id,
            RecommendationTask.recommendation_type == recommendation_type,
            RecommendationTask.status.in_(ACTIVE_TASK_STATUSES),
        )
    ):
        if task.verification_spec.get("opportunity_scope_key") == evaluation.scope_key:
            return task, False

    issue_ids = _validated_issue_ids(db, evaluation)
    primary_issue_id = issue_ids[0] if issue_ids else None
    title = PATTERN_LABELS.get(pattern, "Onderzoek en benut deze SEO-kans")
    task = RecommendationTask(
        website_id=evaluation.website_id,
        created_by_user_id=principal.user_id,
        primary_issue_id=primary_issue_id,
        recommendation_type=recommendation_type,
        definition_version="opportunity-2026-08-v1",
        title=title,
        category="opportunity",
        primary_role="seo_specialist",
        supporting_roles=["content_editor"],
        priority=PRIORITIES.get(evaluation.priority_class, "low"),
        priority_reason=(
            f"Kansscore {evaluation.total_score:.1f}/100; klasse "
            f"{evaluation.priority_class.replace('_', ' ')}."
        ),
        effort_min_minutes=30,
        effort_max_minutes=120,
        effort_confidence="low",
        feasibility="manual_review",
        action=title,
        rationale=(
            "Deze taak is gebaseerd op een transparante kansscore en moet vóór uitvoering "
            "inhoudelijk worden beoordeeld."
        ),
        steps=[
            "Controleer de brondata en bijdragers bij de kansscore.",
            "Bepaal de kleinste passende wijziging en leg de nulmeting vast.",
            "Voer de wijziging uit en beoordeel het resultaat in een volgende meetperiode.",
        ],
        required_input=[
            "Brondata uit de kansbeoordeling",
            "Inhoudelijke beoordeling door een specialist",
        ],
        acceptance_criteria=[
            "De gekozen actie en nulmeting zijn vastgelegd.",
            "De wijziging is gecontroleerd en kan in een volgende periode worden vergeleken.",
        ],
        verification_spec={
            "automated": False,
            "opportunity_evaluation_id": str(evaluation.id),
            "opportunity_scope_key": evaluation.scope_key,
            "formula_version": evaluation.formula_version,
            "pattern": pattern,
        },
    )
    db.add(task)
    db.flush()
    for issue_id in issue_ids:
        db.add(RecommendationTaskIssue(task_id=task.id, issue_id=issue_id))
    if evaluation.primary_url_id and db.scalar(
        select(Url.id).where(
            Url.id == evaluation.primary_url_id, Url.website_id == evaluation.website_id
        )
    ):
        db.add(
            RecommendationTaskUrl(task_id=task.id, url_id=evaluation.primary_url_id, role="page")
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
                details={"opportunity_evaluation_id": str(evaluation.id)},
            ),
            ActivityLog(
                website_id=evaluation.website_id,
                actor=label,
                activity_type="opportunity_task_created",
                summary=f"Kans gepromoveerd naar taak: {task.title}",
                details={"task_id": str(task.id), "evaluation_id": str(evaluation.id)},
            ),
        ]
    )
    db.commit()
    db.refresh(task)
    return task, True


def _validated_issue_ids(db: Session, evaluation: OpportunityEvaluation) -> list[UUID]:
    candidates: list[str] = []
    for item in evaluation.evidence:
        values = item.get("issue_ids")
        if isinstance(values, list):
            candidates.extend(str(value) for value in values)
    if not candidates:
        return []
    return list(
        db.scalars(
            select(Issue.id).where(
                Issue.website_id == evaluation.website_id, Issue.id.in_(candidates)
            )
        )
    )

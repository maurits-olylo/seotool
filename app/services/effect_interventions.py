import hashlib
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.content_analysis import UrlContentClassification, UrlContentOverride
from app.models.effects import EffectIntervention
from app.models.recommendations import RecommendationTask, RecommendationTaskUrl

INTERVENTION_VERSION = "1"


def materialize_task_intervention(
    db: Session, task: RecommendationTask
) -> EffectIntervention | None:
    """Freeze the explainable task scope when it first becomes measurable."""
    if task.status not in {"implemented", "closed"} or task.implemented_at is None:
        return None

    existing = db.scalar(select(EffectIntervention).where(EffectIntervention.task_id == task.id))
    if existing is not None:
        return existing

    task_urls = list(
        db.scalars(
            select(RecommendationTaskUrl)
            .where(RecommendationTaskUrl.task_id == task.id)
            .order_by(RecommendationTaskUrl.url_id, RecommendationTaskUrl.role)
        )
    )
    if not task_urls:
        return None

    url_context = [
        _url_context(db, item.url_id, item.role, implemented_at=task.implemented_at)
        for item in task_urls
    ]
    task_snapshot: dict[str, object] = {
        "recommendation_type": task.recommendation_type,
        "definition_version": task.definition_version,
        "category": task.category,
        "title": task.title,
        "primary_issue_id": str(task.primary_issue_id) if task.primary_issue_id else None,
    }
    payload = {
        "task_id": str(task.id),
        "implemented_at": task.implemented_at.isoformat(),
        "task": task_snapshot,
        "urls": url_context,
    }
    input_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    classified = sum(1 for item in url_context if item["classification_id"] is not None)
    intervention = EffectIntervention(
        website_id=task.website_id,
        task_id=task.id,
        implemented_at=task.implemented_at,
        intervention_version=INTERVENTION_VERSION,
        input_hash=input_hash,
        task_snapshot=task_snapshot,
        url_context=url_context,
        source_coverage={
            "task": True,
            "url_scope": True,
            "classified_urls": classified,
            "total_urls": len(url_context),
        },
    )
    db.add(intervention)
    db.flush()
    return intervention


def _url_context(
    db: Session, url_id: UUID, role: str, *, implemented_at: datetime
) -> dict[str, object]:
    classification = db.scalar(
        select(UrlContentClassification)
        .where(
            UrlContentClassification.url_id == url_id,
            UrlContentClassification.created_at <= implemented_at,
        )
        .order_by(UrlContentClassification.created_at.desc())
        .limit(1)
    )
    override = db.scalar(
        select(UrlContentOverride).where(
            UrlContentOverride.url_id == url_id,
            UrlContentOverride.is_locked.is_(True),
            UrlContentOverride.updated_at <= implemented_at,
        )
    )
    return {
        "url_id": str(url_id),
        "role": role,
        "classification_id": str(classification.id) if classification else None,
        "classification_version": (
            classification.classification_version if classification else None
        ),
        "search_intent": _effective_value(override, classification, "search_intent"),
        "journey_stage": _effective_value(override, classification, "journey_stage"),
        "content_role": _effective_value(override, classification, "content_role"),
        "classification_confidence": classification.confidence if classification else None,
        "override_id": str(override.id) if override else None,
    }


def _effective_value(
    override: UrlContentOverride | None,
    classification: UrlContentClassification | None,
    field: str,
) -> str | None:
    override_value = getattr(override, field, None)
    if override_value:
        return str(override_value)
    classification_value = getattr(classification, field, None)
    return str(classification_value) if classification_value else None

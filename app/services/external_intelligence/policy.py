import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.external_intelligence import (
    ExternalIntelligenceRequest,
    ExternalObservation,
    ExternalUsageRecord,
)
from app.models.website import WebsiteSettings
from app.services.external_intelligence.contracts import QuestionEvidenceRequest

AdmissionStatus = Literal[
    "created",
    "disabled",
    "cached",
    "duplicate",
    "budget_exceeded",
    "scope_limit_reached",
]
ACTIVE_STATUSES = ("pending", "running")


@dataclass(frozen=True)
class ExternalRequestAdmission:
    status: AdmissionStatus
    request: ExternalIntelligenceRequest | None = None
    observation: ExternalObservation | None = None
    spent_micros: int = 0
    reserved_micros: int = 0


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _costs(db: Session, website_id: UUID, now: datetime) -> tuple[int, int]:
    spent = db.scalar(
        select(func.coalesce(func.sum(ExternalUsageRecord.actual_cost_micros), 0)).where(
            ExternalUsageRecord.website_id == website_id,
            ExternalUsageRecord.recorded_at >= _month_start(now),
        )
    )
    reserved = db.scalar(
        select(func.coalesce(func.sum(ExternalIntelligenceRequest.estimated_cost_micros), 0)).where(
            ExternalIntelligenceRequest.website_id == website_id,
            ExternalIntelligenceRequest.status.in_(ACTIVE_STATUSES),
        )
    )
    return int(spent or 0), int(reserved or 0)


def _active_scope_keys(db: Session, website_id: UUID, now: datetime) -> set[str]:
    observations = db.scalars(
        select(ExternalObservation.cache_key).where(
            ExternalObservation.website_id == website_id,
            ExternalObservation.expires_at > now,
        )
    )
    requests = db.scalars(
        select(ExternalIntelligenceRequest.cache_key).where(
            ExternalIntelligenceRequest.website_id == website_id,
            ExternalIntelligenceRequest.status.in_(ACTIVE_STATUSES),
        )
    )
    return set(observations) | set(requests)


def _idempotency_key(capability: str, cache_key: str, now: datetime) -> str:
    value = f"{capability}|{cache_key}|{now.date().isoformat()}"
    return hashlib.sha256(value.encode()).hexdigest()


def admit_external_request(
    db: Session,
    *,
    website_id: UUID,
    url_id: UUID | None,
    capability: str,
    context: QuestionEvidenceRequest,
    reason: str,
    provider: str | None,
    estimated_cost_micros: int,
    now: datetime | None = None,
) -> ExternalRequestAdmission:
    """Apply cache, idempotency, scope and budget guards before any provider call."""
    if capability not in {"serp", "ai_citations"}:
        raise ValueError("Unsupported external intelligence capability")
    if estimated_cost_micros < 0:
        raise ValueError("Estimated cost must not be negative")
    current_time = now or datetime.now(UTC)
    settings = db.get(WebsiteSettings, website_id)
    if not settings or not settings.external_intelligence_enabled:
        return ExternalRequestAdmission(status="disabled")

    cached = db.scalar(
        select(ExternalObservation)
        .where(
            ExternalObservation.website_id == website_id,
            ExternalObservation.capability == capability,
            ExternalObservation.cache_key == context.cache_key,
            ExternalObservation.expires_at > current_time,
        )
        .order_by(ExternalObservation.observed_at.desc())
        .limit(1)
    )
    if cached:
        return ExternalRequestAdmission(status="cached", observation=cached)

    key = _idempotency_key(capability, context.cache_key, current_time)
    duplicate = db.scalar(
        select(ExternalIntelligenceRequest).where(
            ExternalIntelligenceRequest.website_id == website_id,
            ExternalIntelligenceRequest.capability == capability,
            ExternalIntelligenceRequest.idempotency_key == key,
        )
    )
    if duplicate:
        return ExternalRequestAdmission(status="duplicate", request=duplicate)

    active_scopes = _active_scope_keys(db, website_id, current_time)
    if (
        context.cache_key not in active_scopes
        and len(active_scopes) >= settings.external_active_scope_limit
    ):
        return ExternalRequestAdmission(status="scope_limit_reached")

    spent, reserved = _costs(db, website_id, current_time)
    if spent + reserved + estimated_cost_micros > settings.external_monthly_budget_micros:
        return ExternalRequestAdmission(
            status="budget_exceeded",
            spent_micros=spent,
            reserved_micros=reserved,
        )

    request = ExternalIntelligenceRequest(
        website_id=website_id,
        url_id=url_id,
        capability=capability,
        cache_key=context.cache_key,
        idempotency_key=key,
        reason=reason,
        provider=provider,
        request_context={
            "question": context.question,
            "language": context.language,
            "country": context.country,
            "device": context.device,
            "location": context.location,
        },
        budget_snapshot={
            "monthly_limit_micros": settings.external_monthly_budget_micros,
            "spent_micros": spent,
            "reserved_micros": reserved,
            "active_scope_limit": settings.external_active_scope_limit,
        },
        estimated_cost_micros=estimated_cost_micros,
    )
    db.add(request)
    db.flush()
    return ExternalRequestAdmission(
        status="created",
        request=request,
        spent_micros=spent,
        reserved_micros=reserved,
    )

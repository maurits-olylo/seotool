import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.external_intelligence import (
    ExternalIntelligenceRequest,
    ExternalObservation,
    ExternalUsageRecord,
)
from app.services.external_intelligence.contracts import (
    AiCitationObservation,
    Device,
    ProviderUsage,
    QuestionEvidenceRequest,
    SerpObservation,
    SourceReference,
)
from app.services.external_intelligence.providers.dataforseo import DataForSeoResponseError
from app.services.external_intelligence.providers.dataforseo_client import DataForSeoClient

FRESHNESS = timedelta(days=7)


def execute_queued_external_request(request_id: str) -> None:
    with SessionLocal() as db:
        request = db.get(ExternalIntelligenceRequest, UUID(request_id))
        if request and request.status == "failed":
            request.status = "pending"
            request.finished_at = None
            request.error_code = None
            db.commit()
        asyncio.run(
            execute_external_request(
                db,
                request_id=UUID(request_id),
                provider=DataForSeoClient(),
            )
        )


class ExternalEvidenceProvider(Protocol):
    async def fetch_serp(
        self, request: QuestionEvidenceRequest
    ) -> tuple[SerpObservation, ProviderUsage]: ...

    async def fetch_citations(
        self, request: QuestionEvidenceRequest
    ) -> tuple[tuple[AiCitationObservation, ...], ProviderUsage]: ...


async def execute_external_request(
    db: Session,
    *,
    request_id: UUID,
    provider: ExternalEvidenceProvider,
    now: datetime | None = None,
) -> ExternalObservation:
    """Claim one admitted request and atomically persist its normalized result and usage."""
    current_time = now or datetime.now(UTC)
    request = _claim(db, request_id=request_id, now=current_time)

    try:
        context = _context(request.request_context)
        if request.capability == "serp":
            serp, usage = await provider.fetch_serp(context)
            payload = _serp_payload(serp)
            observed_at = serp.observed_at
            source_coverage = {
                "serp": bool(serp.organic_results),
                "organic_results": len(serp.organic_results),
                "warnings": list(serp.warnings),
            }
        elif request.capability == "ai_citations":
            citations, usage = await provider.fetch_citations(context)
            payload = _citations_payload(citations)
            observed_at = max(
                (item.observed_at for item in citations),
                default=current_time,
            )
            source_coverage = {
                "ai_citations": bool(citations),
                "observations": len(citations),
                "cited_sources": sum(len(item.sources) for item in citations),
            }
        else:
            raise ValueError("Unsupported external intelligence capability")
        return _complete(
            db,
            request_id=request.id,
            payload=payload,
            usage=usage,
            observed_at=observed_at,
            source_coverage=source_coverage,
            now=current_time,
        )
    except Exception as error:
        db.rollback()
        _fail(db, request_id=request.id, error=error, now=current_time)
        raise


def _claim(
    db: Session, *, request_id: UUID, now: datetime
) -> ExternalIntelligenceRequest:
    request = db.scalar(
        select(ExternalIntelligenceRequest)
        .where(ExternalIntelligenceRequest.id == request_id)
        .with_for_update()
    )
    if request is None:
        raise ValueError("External intelligence request does not exist")
    if request.status != "pending":
        raise ValueError("External intelligence request is not pending")
    request.status = "running"
    request.started_at = now
    db.commit()
    return request


def _complete(
    db: Session,
    *,
    request_id: UUID,
    payload: dict[str, object],
    usage: ProviderUsage,
    observed_at: datetime,
    source_coverage: dict[str, object],
    now: datetime,
) -> ExternalObservation:
    request = db.scalar(
        select(ExternalIntelligenceRequest)
        .where(ExternalIntelligenceRequest.id == request_id)
        .with_for_update()
    )
    if request is None or request.status != "running":
        raise ValueError("External intelligence request is no longer running")
    if usage.provider != request.provider:
        raise ValueError("Provider usage does not match the admitted request")

    input_hash = _hash(request.request_context)
    evidence_hash = _hash(payload)
    observation = ExternalObservation(
        website_id=request.website_id,
        request_id=request.id,
        capability=request.capability,
        cache_key=request.cache_key,
        provider=usage.provider,
        observed_at=observed_at,
        expires_at=observed_at + FRESHNESS,
        input_hash=input_hash,
        evidence_hash=evidence_hash,
        normalized_payload=payload,
        source_coverage=source_coverage,
    )
    db.add_all(
        [
            observation,
            ExternalUsageRecord(
                website_id=request.website_id,
                request_id=request.id,
                capability=request.capability,
                provider=usage.provider,
                units=usage.units,
                estimated_cost_micros=request.estimated_cost_micros,
                actual_cost_micros=usage.cost_micros,
                currency=usage.currency,
                recorded_at=now,
            ),
        ]
    )
    request.status = "succeeded"
    request.actual_cost_micros = usage.cost_micros
    request.currency = usage.currency
    request.finished_at = now
    request.error_code = None
    db.commit()
    db.refresh(observation)
    return observation


def _fail(db: Session, *, request_id: UUID, error: Exception, now: datetime) -> None:
    request = db.scalar(
        select(ExternalIntelligenceRequest)
        .where(ExternalIntelligenceRequest.id == request_id)
        .with_for_update()
    )
    if request is None or request.status != "running":
        return
    request.status = "failed"
    request.finished_at = now
    request.error_code = (
        "provider_response_invalid"
        if isinstance(error, DataForSeoResponseError)
        else "execution_failed"
    )
    db.commit()


def _context(value: dict[str, object]) -> QuestionEvidenceRequest:
    return QuestionEvidenceRequest(
        question=str(value.get("question") or ""),
        language=str(value.get("language") or ""),
        country=str(value.get("country") or ""),
        device=_device(value.get("device")),
        location=str(value["location"]) if value.get("location") else None,
    )


def _device(value: object) -> Device:
    if value not in {"desktop", "mobile"}:
        raise ValueError("Stored external intelligence device is invalid")
    return value


def _serp_payload(observation: SerpObservation) -> dict[str, object]:
    return {
        "observed_at": observation.observed_at.isoformat(),
        "organic_results": [_source_payload(item) for item in observation.organic_results],
        "features": list(observation.features),
        "warnings": list(observation.warnings),
    }


def _citations_payload(
    observations: tuple[AiCitationObservation, ...],
) -> dict[str, object]:
    return {
        "observations": [
            {
                "observed_at": item.observed_at.isoformat(),
                "platform": item.platform,
                "observed_question": item.observed_question,
                "sources": [_source_payload(source) for source in item.sources],
                "answer_excerpt": item.answer_excerpt,
                "warnings": list(item.warnings),
            }
            for item in observations
        ]
    }


def _source_payload(source: SourceReference) -> dict[str, object]:
    return {
        "url": source.url,
        "title": source.title,
        "position": source.position,
    }


def _hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()

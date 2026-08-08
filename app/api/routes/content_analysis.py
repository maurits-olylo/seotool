from dataclasses import asdict
from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.queue import enqueue_external_intelligence
from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.models.content_analysis import ContentAnalysisSettings, UrlContentOverride
from app.models.crawl import UrlSnapshot
from app.models.discovery import Url
from app.models.external_intelligence import (
    ExternalIntelligenceRequest,
    ExternalObservation,
    ExternalUsageRecord,
)
from app.models.website import WebsiteSettings
from app.schemas.content_analysis import (
    ContentAnalysisSettingsData,
    ContentOverrideRead,
    ContentOverrideWrite,
)
from app.schemas.external_intelligence import (
    ExternalEvidenceControlsRead,
    ExternalEvidenceControlsUpdate,
    ExternalEvidenceCreate,
    ExternalEvidenceResult,
    ExternalEvidenceState,
)
from app.services.analytics_journey import build_analytics_journey
from app.services.authorization import require_website_access, require_website_write_access
from app.services.content_analysis import analyze_website_content
from app.services.content_opportunities import (
    build_content_opportunities,
    create_opportunity_task,
    create_question_gap_task,
)
from app.services.external_intelligence.contracts import QuestionEvidenceRequest
from app.services.external_intelligence.interpretation import assess_stored_citation_evidence
from app.services.external_intelligence.policy import admit_external_request
from app.services.external_intelligence.presentation import public_stored_ai_evidence
from app.services.question_coverage import assess_question_coverage
from app.services.question_scope_selection import select_question_scopes
from app.services.security_audit import record_security_event

router = APIRouter(prefix="/websites/{website_id}/content-analysis", tags=["content-analysis"])


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _external_evidence_controls(
    db: Session, website_id: UUID
) -> ExternalEvidenceControlsRead:
    app_settings = get_settings()
    website_settings = db.get(WebsiteSettings, website_id)
    estimate = app_settings.external_ai_citations_estimated_cost_micros
    budget = website_settings.external_monthly_budget_micros if website_settings else 0
    now = datetime.now(UTC)
    completed = db.scalar(
        select(func.count(ExternalUsageRecord.id)).where(
            ExternalUsageRecord.website_id == website_id,
            ExternalUsageRecord.capability == "ai_citations",
            ExternalUsageRecord.recorded_at >= _month_start(now),
        )
    )
    active_request_keys = set(
        db.scalars(
            select(ExternalIntelligenceRequest.cache_key).where(
                ExternalIntelligenceRequest.website_id == website_id,
                ExternalIntelligenceRequest.capability == "ai_citations",
                ExternalIntelligenceRequest.status.in_(("pending", "running")),
            )
        )
    )
    active_observation_keys = set(
        db.scalars(
            select(ExternalObservation.cache_key).where(
                ExternalObservation.website_id == website_id,
                ExternalObservation.capability == "ai_citations",
                ExternalObservation.expires_at > now,
            )
        )
    )
    in_progress = db.scalar(
        select(func.count(ExternalIntelligenceRequest.id)).where(
            ExternalIntelligenceRequest.website_id == website_id,
            ExternalIntelligenceRequest.capability == "ai_citations",
            ExternalIntelligenceRequest.status.in_(("pending", "running")),
        )
    )
    return ExternalEvidenceControlsRead(
        available=bool(app_settings.dataforseo_enabled and estimate > 0),
        enabled=bool(website_settings and website_settings.external_intelligence_enabled),
        monthly_check_limit=budget // estimate if estimate > 0 else 0,
        active_question_limit=(
            website_settings.external_active_scope_limit if website_settings else 0
        ),
        checks_completed_this_month=int(completed or 0),
        checks_in_progress=int(in_progress or 0),
        active_questions=len(active_request_keys | active_observation_keys),
    )


def _url_for_website(db: Session, website_id: UUID, url_id: UUID) -> Url:
    url = db.get(Url, url_id)
    if not url or url.website_id != website_id:
        raise HTTPException(status_code=404, detail="URL not found")
    return url


@router.post("/classify")
def classify_website_content(
    website_id: UUID,
    period_start: date,
    period_end: date,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, int]:
    require_website_write_access(db, principal, website_id)
    if period_start > period_end:
        raise HTTPException(status_code=422, detail="Start date must not be after end date")
    return analyze_website_content(db, website_id, period_start, period_end)


@router.get("/opportunities")
def content_opportunities(
    website_id: UUID,
    period_start: date,
    period_end: date,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    require_website_access(db, principal, website_id)
    if period_start > period_end:
        raise HTTPException(status_code=422, detail="Start date must not be after end date")
    return build_content_opportunities(db, website_id, period_start, period_end)


@router.get("/journey")
def analytics_journey(
    website_id: UUID,
    period_start: date,
    period_end: date,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    require_website_access(db, principal, website_id)
    if period_start > period_end:
        raise HTTPException(status_code=422, detail="Start date must not be after end date")
    return build_analytics_journey(db, website_id, period_start, period_end)


@router.get("/question-scopes")
def question_scopes(
    website_id: UUID,
    period_start: date,
    period_end: date,
    max_pages: int = Query(default=25, ge=1, le=100),
    max_questions_per_page: int = Query(default=3, ge=1, le=10),
    max_pages_per_family: int = Query(default=5, ge=1, le=20),
    max_total: int = Query(default=60, ge=1, le=500),
    minimum_impressions: int = Query(default=25, ge=1),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    require_website_access(db, principal, website_id)
    if period_start > period_end:
        raise HTTPException(status_code=422, detail="Start date must not be after end date")
    selection = select_question_scopes(
        db,
        website_id=website_id,
        period_start=period_start,
        period_end=period_end,
        max_pages=max_pages,
        max_questions_per_page=max_questions_per_page,
        max_pages_per_family=max_pages_per_family,
        max_total=max_total,
        minimum_impressions=minimum_impressions,
    )
    website_settings = db.get(WebsiteSettings, website_id)
    return {
        **asdict(selection),
        "external_evidence_available": bool(
            get_settings().dataforseo_enabled
            and website_settings
            and website_settings.external_intelligence_enabled
        ),
    }


@router.get("/external-evidence-controls", response_model=ExternalEvidenceControlsRead)
def external_evidence_controls(
    website_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> ExternalEvidenceControlsRead:
    require_website_access(db, principal, website_id)
    return _external_evidence_controls(db, website_id)


@router.put("/external-evidence-controls", response_model=ExternalEvidenceControlsRead)
def update_external_evidence_controls(
    website_id: UUID,
    payload: ExternalEvidenceControlsUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> ExternalEvidenceControlsRead:
    require_website_write_access(db, principal, website_id)
    app_settings = get_settings()
    if payload.enabled and not app_settings.dataforseo_enabled:
        raise HTTPException(status_code=409, detail="Extra evidence is not available")
    settings = db.get(WebsiteSettings, website_id)
    if not settings:
        raise HTTPException(status_code=404, detail="Website settings not found")
    settings.external_intelligence_enabled = payload.enabled
    settings.external_active_scope_limit = payload.active_question_limit
    settings.external_monthly_budget_micros = (
        payload.monthly_check_limit
        * app_settings.external_ai_citations_estimated_cost_micros
    )
    db.commit()
    return _external_evidence_controls(db, website_id)


@router.post("/external-evidence", response_model=ExternalEvidenceState, status_code=202)
def request_external_evidence(
    website_id: UUID,
    payload: ExternalEvidenceCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> ExternalEvidenceState:
    require_website_write_access(db, principal, website_id)
    settings = get_settings()
    if not settings.dataforseo_enabled:
        raise HTTPException(status_code=503, detail="External evidence is not available")
    if payload.url_id:
        _url_for_website(db, website_id, payload.url_id)
    estimate = (
        settings.external_serp_estimated_cost_micros
        if payload.capability == "serp"
        else settings.external_ai_citations_estimated_cost_micros
    )
    admission = admit_external_request(
        db,
        website_id=website_id,
        url_id=payload.url_id,
        capability=payload.capability,
        context=QuestionEvidenceRequest(
            question=payload.question,
            language=payload.language,
            country=payload.country,
            device=payload.device,
            location=payload.location or _external_location(payload.country),
        ),
        reason="human_selected_question",
        provider="dataforseo",
        estimated_cost_micros=estimate,
    )
    if admission.status == "disabled":
        raise HTTPException(status_code=409, detail="External evidence is not enabled")
    if admission.status in {"budget_exceeded", "scope_limit_reached"}:
        return ExternalEvidenceState(status=admission.status, capability=payload.capability)
    if admission.status == "cached" and admission.observation:
        return ExternalEvidenceState(
            observation_id=admission.observation.id,
            status="available",
            capability=payload.capability,
        )
    if admission.status == "duplicate" and admission.request:
        observation_id = db.scalar(
            select(ExternalObservation.id).where(
                ExternalObservation.request_id == admission.request.id
            )
        )
        return _external_state(admission.request, observation_id=observation_id)
    if not admission.request:
        raise HTTPException(status_code=500, detail="External evidence request failed")
    db.commit()
    if not enqueue_external_intelligence(
        str(admission.request.id), website_id=str(website_id)
    ):
        admission.request.status = "cancelled"
        admission.request.finished_at = datetime.now(UTC)
        db.commit()
        raise HTTPException(status_code=503, detail="External evidence queue is unavailable")
    return ExternalEvidenceState(
        request_id=admission.request.id,
        status="queued",
        capability=payload.capability,
    )


@router.get(
    "/external-evidence/{request_id}", response_model=ExternalEvidenceState
)
def external_evidence_status(
    website_id: UUID,
    request_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> ExternalEvidenceState:
    require_website_access(db, principal, website_id)
    request = db.get(ExternalIntelligenceRequest, request_id)
    if not request or request.website_id != website_id:
        raise HTTPException(status_code=404, detail="External evidence request not found")
    observation_id = db.scalar(
        select(ExternalObservation.id).where(ExternalObservation.request_id == request.id)
    )
    return _external_state(request, observation_id=observation_id)


@router.get(
    "/external-evidence/observations/{observation_id}",
    response_model=ExternalEvidenceResult,
)
def external_evidence_result(
    website_id: UUID,
    observation_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    require_website_access(db, principal, website_id)
    observation = db.get(ExternalObservation, observation_id)
    if (
        not observation
        or observation.website_id != website_id
        or observation.capability != "ai_citations"
    ):
        raise HTTPException(status_code=404, detail="Bewijs niet gevonden")
    request = db.get(ExternalIntelligenceRequest, observation.request_id)
    if not request or request.status != "succeeded":
        raise HTTPException(status_code=409, detail="Bewijs is nog niet beschikbaar")
    question = str(request.request_context.get("question") or "")
    assessment = None
    coverage_status = None
    if request.url_id:
        url = db.get(Url, request.url_id)
        snapshot = db.scalar(
            select(UrlSnapshot)
            .where(UrlSnapshot.url_id == request.url_id)
            .order_by(UrlSnapshot.checked_at.desc())
            .limit(1)
        )
        if url and snapshot:
            coverage = assess_question_coverage(
                question,
                title=snapshot.title,
                headings=snapshot.headings,
                meta_description=snapshot.meta_description,
                main_content=snapshot.main_content,
            )
            raw_observations = observation.normalized_payload.get("observations", [])
            citation_urls = tuple(
                str(source["url"])
                for item in raw_observations
                if isinstance(item, dict)
                for source in item.get("sources", [])
                if isinstance(source, dict) and isinstance(source.get("url"), str)
            ) if isinstance(raw_observations, list) else ()
            assessment = assess_stored_citation_evidence(
                page_url=url.normalized_url,
                coverage=coverage,
                question=question,
                citation_urls=citation_urls,
                observation_count=(
                    len(raw_observations) if isinstance(raw_observations, list) else 0
                ),
            )
            coverage_status = coverage.status
    return public_stored_ai_evidence(
        observation,
        question=question,
        assessment=assessment,
        coverage_status=coverage_status,
    )


@router.post("/external-evidence/observations/{observation_id}/task", status_code=201)
def create_external_evidence_task(
    website_id: UUID,
    observation_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    require_website_write_access(db, principal, website_id)
    result = external_evidence_result(website_id, observation_id, db, principal)
    assessment = result.get("assessment")
    observation = db.get(ExternalObservation, observation_id)
    request = db.get(ExternalIntelligenceRequest, observation.request_id) if observation else None
    if (
        not isinstance(assessment, dict)
        or assessment.get("status") != "observed_citation_gap"
        or not assessment.get("recommended_action")
        or not request
        or not request.url_id
    ):
        raise HTTPException(status_code=409, detail="Voor deze meting is geen inhoudstaak nodig")
    task, created = create_question_gap_task(
        db,
        website_id=website_id,
        url_id=request.url_id,
        question=str(result["question"]),
        summary=str(assessment["summary"]),
        recommended_action=str(assessment["recommended_action"]),
        observation_id=observation_id,
        principal=principal,
    )
    return {"task_id": str(task.id), "created": created}


def _external_state(
    request: ExternalIntelligenceRequest, *, observation_id: UUID | None = None
) -> ExternalEvidenceState:
    public_status = "available" if request.status == "succeeded" else request.status
    return ExternalEvidenceState(
        request_id=request.id,
        observation_id=observation_id,
        status=public_status,  # type: ignore[arg-type]
        capability=request.capability,  # type: ignore[arg-type]
    )


def _external_location(country: str) -> str:
    locations = {
        "BE": "Belgium",
        "DE": "Germany",
        "FR": "France",
        "GB": "United Kingdom",
        "NL": "Netherlands",
        "US": "United States",
    }
    try:
        return locations[country.upper()]
    except KeyError as error:
        raise HTTPException(
            status_code=422,
            detail="Deze meetlocatie wordt nog niet ondersteund voor extra bewijs",
        ) from error


@router.post("/opportunities/{opportunity_key}/task", status_code=201)
def promote_content_opportunity(
    website_id: UUID,
    opportunity_key: str,
    period_start: date,
    period_end: date,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    require_website_write_access(db, principal, website_id)
    if period_start > period_end:
        raise HTTPException(status_code=422, detail="Start date must not be after end date")
    analysis = build_content_opportunities(db, website_id, period_start, period_end)
    opportunity = next(
        (item for item in analysis["opportunities"] if item["key"] == opportunity_key),
        None,
    )
    if not opportunity:
        raise HTTPException(status_code=404, detail="Content opportunity not found")
    task, created = create_opportunity_task(
        db,
        website_id=website_id,
        opportunity=opportunity,
        principal=principal,
    )
    return {"task_id": str(task.id), "created": created}


@router.get("/settings", response_model=ContentAnalysisSettingsData)
def get_content_settings(
    website_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> ContentAnalysisSettingsData | ContentAnalysisSettings:
    require_website_access(db, principal, website_id)
    return db.get(ContentAnalysisSettings, website_id) or ContentAnalysisSettingsData(
        website_id=website_id
    )


@router.put("/settings", response_model=ContentAnalysisSettingsData)
def update_content_settings(
    website_id: UUID,
    payload: ContentAnalysisSettingsData,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> ContentAnalysisSettings:
    require_website_write_access(db, principal, website_id)
    settings = db.get(ContentAnalysisSettings, website_id) or ContentAnalysisSettings(
        website_id=website_id
    )
    settings.branded_terms = payload.branded_terms
    settings.sector_template = payload.sector_template
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


@router.put("/urls/{url_id}/override", response_model=ContentOverrideRead)
def set_content_override(
    website_id: UUID,
    url_id: UUID,
    payload: ContentOverrideWrite,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> UrlContentOverride:
    website = require_website_write_access(db, principal, website_id)
    _url_for_website(db, website_id, url_id)
    override = db.scalar(select(UrlContentOverride).where(UrlContentOverride.url_id == url_id))
    if not override:
        override = UrlContentOverride(website_id=website_id, url_id=url_id)
    for key, value in payload.model_dump().items():
        setattr(override, key, value)
    override.updated_by_user_id = principal.user_id
    db.add(override)
    record_security_event(
        db,
        event_type="content_override_changed",
        result="success",
        summary="Content classification override changed",
        actor_user_id=principal.user_id,
        client_id=website.client_id,
        target_type="url",
        target_id=url_id,
        details={"website_id": str(website_id), "locked": payload.is_locked},
    )
    db.commit()
    db.refresh(override)
    return override


@router.delete("/urls/{url_id}/override", status_code=status.HTTP_204_NO_CONTENT)
def reset_content_override(
    website_id: UUID,
    url_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> Response:
    website = require_website_write_access(db, principal, website_id)
    _url_for_website(db, website_id, url_id)
    override = db.scalar(select(UrlContentOverride).where(UrlContentOverride.url_id == url_id))
    if override:
        db.delete(override)
        record_security_event(
            db,
            event_type="content_override_reset",
            result="success",
            summary="Content classification override reset",
            actor_user_id=principal.user_id,
            client_id=website.client_id,
            target_type="url",
            target_id=url_id,
            details={"website_id": str(website_id)},
        )
        db.commit()
    return Response(status_code=204)

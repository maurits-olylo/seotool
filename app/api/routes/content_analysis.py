from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.models.content_analysis import ContentAnalysisSettings, UrlContentOverride
from app.models.discovery import Url
from app.schemas.content_analysis import (
    ContentAnalysisSettingsData,
    ContentOverrideRead,
    ContentOverrideWrite,
)
from app.services.authorization import require_website_access, require_website_write_access
from app.services.content_analysis import analyze_website_content
from app.services.security_audit import record_security_event

router = APIRouter(prefix="/websites/{website_id}/content-analysis", tags=["content-analysis"])


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

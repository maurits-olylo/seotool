from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.models.onboarding import WebsiteOnboarding
from app.schemas.onboarding import (
    WebsiteOnboardingCrawlPreferences,
    WebsiteOnboardingDetailsUpdate,
    WebsiteOnboardingFirstCrawlRead,
    WebsiteOnboardingRead,
    WebsiteOnboardingStart,
    WebsitePlatformConfirm,
    WebsitePlatformRead,
    WebsiteVerificationCheckRead,
)
from app.services.authorization import require_client_access
from app.services.website_onboarding import (
    check_website_ownership,
    confirm_website_platform,
    create_wordpress_verification_plugin,
    detect_website_platform,
    get_website_onboarding,
    renew_website_verification_file,
    retry_first_onboarding_crawl,
    start_first_onboarding_crawl,
    start_website_onboarding,
    update_website_onboarding_details,
)

router = APIRouter(prefix="/website-onboarding", tags=["website-onboarding"])


def _platform_read(onboarding: WebsiteOnboarding) -> WebsitePlatformRead:
    return WebsitePlatformRead(
        detected_platform=onboarding.detected_platform,
        platform_confidence=onboarding.platform_confidence,
        confirmed_platform=onboarding.confirmed_platform,
    )


@router.post(
    "/clients/{client_id}",
    response_model=WebsiteOnboardingRead,
    status_code=status.HTTP_201_CREATED,
)
def start_onboarding(
    client_id: UUID,
    payload: WebsiteOnboardingStart,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> WebsiteOnboardingRead:
    require_client_access(db, principal, client_id, admin=True)
    try:
        return start_website_onboarding(
            db,
            client_id=client_id,
            actor_user_id=principal.user_id,
            payload=payload,
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Website of onboarding bestaat al") from exc


@router.get("/{onboarding_id}", response_model=WebsiteOnboardingRead)
def onboarding_status(
    onboarding_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> WebsiteOnboardingRead:
    onboarding = _authorized_onboarding(db, principal, onboarding_id)
    try:
        return get_website_onboarding(db, onboarding.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{onboarding_id}/details", response_model=WebsiteOnboardingRead)
def update_onboarding_details(
    onboarding_id: UUID,
    payload: WebsiteOnboardingDetailsUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> WebsiteOnboardingRead:
    onboarding = _authorized_onboarding(db, principal, onboarding_id, admin=True)
    try:
        return update_website_onboarding_details(db, onboarding.id, payload)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Deze website bestaat al") from exc
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{onboarding_id}/platform/detect", response_model=WebsitePlatformRead)
def detect_platform(
    onboarding_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> WebsitePlatformRead:
    onboarding = _authorized_onboarding(db, principal, onboarding_id, admin=True)
    return _platform_read(detect_website_platform(db, onboarding.id))


@router.post("/{onboarding_id}/platform/confirm", response_model=WebsitePlatformRead)
def confirm_platform(
    onboarding_id: UUID,
    payload: WebsitePlatformConfirm,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> WebsitePlatformRead:
    onboarding = _authorized_onboarding(db, principal, onboarding_id, admin=True)
    return _platform_read(confirm_website_platform(db, onboarding.id, payload.platform))


@router.post("/{onboarding_id}/verification/check", response_model=WebsiteVerificationCheckRead)
def check_verification(
    onboarding_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> WebsiteVerificationCheckRead:
    onboarding = _authorized_onboarding(db, principal, onboarding_id, admin=True)
    try:
        onboarding, verification = check_website_ownership(db, onboarding.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WebsiteVerificationCheckRead(
        onboarding_id=onboarding.id,
        status=onboarding.status,
        current_step=onboarding.current_step,
        verification_status=verification.status,
        attempt_count=verification.attempt_count,
        last_error_code=onboarding.last_error_code,
    )


@router.post("/{onboarding_id}/verification/file", response_class=Response)
def download_new_verification_file(
    onboarding_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> Response:
    onboarding = _authorized_onboarding(db, principal, onboarding_id, admin=True)
    try:
        content = renew_website_verification_file(
            db,
            onboarding.id,
            actor_user_id=principal.user_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'attachment; filename="thactual-verification.txt"',
        },
    )


@router.post("/{onboarding_id}/verification/wordpress-plugin", response_class=Response)
def download_wordpress_plugin(
    onboarding_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> Response:
    onboarding = _authorized_onboarding(db, principal, onboarding_id, admin=True)
    if onboarding.confirmed_platform != "wordpress":
        raise HTTPException(status_code=409, detail="Bevestig eerst WordPress als platform")
    try:
        content = create_wordpress_verification_plugin(
            db, onboarding.id, actor_user_id=principal.user_id
        )
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'attachment; filename="thactual-verification.zip"',
        },
    )


@router.post(
    "/{onboarding_id}/first-crawl",
    response_model=WebsiteOnboardingFirstCrawlRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_first_crawl(
    onboarding_id: UUID,
    payload: WebsiteOnboardingCrawlPreferences,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> WebsiteOnboardingFirstCrawlRead:
    onboarding = _authorized_onboarding(db, principal, onboarding_id, admin=True)
    try:
        onboarding, job = start_first_onboarding_crawl(
            db,
            onboarding.id,
            actor_user_id=principal.user_id,
            preferences=payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return WebsiteOnboardingFirstCrawlRead(
        onboarding_id=onboarding.id,
        website_id=onboarding.website_id,
        crawl_job_id=job.id,
        status=onboarding.status,
        current_step=onboarding.current_step,
        queue_status=job.status,
    )


@router.post(
    "/{onboarding_id}/first-crawl/retry",
    response_model=WebsiteOnboardingFirstCrawlRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_first_crawl(
    onboarding_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> WebsiteOnboardingFirstCrawlRead:
    onboarding = _authorized_onboarding(db, principal, onboarding_id, admin=True)
    try:
        onboarding, job = retry_first_onboarding_crawl(db, onboarding.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return WebsiteOnboardingFirstCrawlRead(
        onboarding_id=onboarding.id,
        website_id=onboarding.website_id,
        crawl_job_id=job.id,
        status=onboarding.status,
        current_step=onboarding.current_step,
        queue_status=job.status,
    )


def _authorized_onboarding(
    db: Session, principal: Principal, onboarding_id: UUID, *, admin: bool = False
) -> WebsiteOnboarding:
    onboarding = db.get(WebsiteOnboarding, onboarding_id)
    if onboarding is None:
        raise HTTPException(status_code=404, detail="Website onboarding not found")
    require_client_access(db, principal, onboarding.client_id, admin=admin)
    return onboarding

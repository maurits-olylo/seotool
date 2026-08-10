import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.queue import crawl_queue_name, enqueue_crawl_job
from app.models.discovery import CrawlJob
from app.models.onboarding import WebsiteOnboarding, WebsiteOwnershipVerification
from app.models.website import Website, WebsiteSettings
from app.schemas.onboarding import (
    WebsiteOnboardingCrawlPreferences,
    WebsiteOnboardingRead,
    WebsiteOnboardingStart,
)
from app.services.crawl_deployment import (
    crawl_deployment_is_active,
    pause_job_if_deployment_active,
)
from app.services.http_crawler import CrawlError, fetch_url
from app.services.security_audit import record_security_event

VERIFICATION_PATH = "/.well-known/thactual-verification.txt"
VERIFICATION_PREFIX = "thactual-site-verification="
VERIFICATION_TTL_DAYS = 7


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_website_onboarding(
    db: Session,
    *,
    client_id: UUID,
    actor_user_id: UUID | None,
    payload: WebsiteOnboardingStart,
) -> WebsiteOnboardingRead:
    existing = db.scalar(
        select(WebsiteOnboarding).where(
            WebsiteOnboarding.client_id == client_id,
            WebsiteOnboarding.request_id == payload.request_id,
        )
    )
    if existing is not None:
        verification = _verification(db, existing.id)
        return _read(existing, verification)

    token = secrets.token_urlsafe(32)
    website = Website(
        client_id=client_id,
        name=payload.website_name,
        base_url=str(payload.base_url),
        language=payload.language,
        country=payload.country.upper() if payload.country else None,
        status="verification_pending",
    )
    website.settings = WebsiteSettings(**payload.settings.model_dump(exclude={"website_id"}))
    db.add(website)
    db.flush()
    onboarding = WebsiteOnboarding(
        client_id=client_id,
        website_id=website.id,
        started_by_user_id=actor_user_id,
        request_id=payload.request_id,
        status="verification_pending",
        current_step="verification",
    )
    db.add(onboarding)
    db.flush()
    verification = WebsiteOwnershipVerification(
        onboarding_id=onboarding.id,
        website_id=website.id,
        token_hash=token_hash(token),
        expires_at=datetime.now(UTC) + timedelta(days=VERIFICATION_TTL_DAYS),
    )
    db.add(verification)
    record_security_event(
        db,
        event_type="website_onboarding.started",
        result="success",
        summary="Website-onboarding gestart; eigendomsverificatie vereist",
        actor_user_id=actor_user_id,
        client_id=client_id,
        target_type="website_onboarding",
        target_id=onboarding.id,
        details={"method": "https_file"},
    )
    db.commit()
    return _read(onboarding, verification, token=token)


def get_website_onboarding(db: Session, onboarding_id: UUID) -> WebsiteOnboardingRead:
    onboarding = db.get(WebsiteOnboarding, onboarding_id)
    if onboarding is None:
        raise LookupError("Website onboarding not found")
    first_crawl_job = (
        db.get(CrawlJob, onboarding.first_crawl_job_id) if onboarding.first_crawl_job_id else None
    )
    return _read(onboarding, _verification(db, onboarding.id), first_crawl_job=first_crawl_job)


def renew_website_verification_file(
    db: Session,
    onboarding_id: UUID,
    *,
    actor_user_id: UUID | None,
) -> str:
    onboarding = db.scalar(
        select(WebsiteOnboarding).where(WebsiteOnboarding.id == onboarding_id).with_for_update()
    )
    if onboarding is None:
        raise LookupError("Website onboarding not found")
    verification = _verification(db, onboarding.id, lock=True)
    if verification.status == "verified":
        raise ValueError("Website is al geverifieerd")

    token = secrets.token_urlsafe(32)
    verification.token_hash = token_hash(token)
    verification.status = "pending"
    verification.attempt_count = 0
    verification.expires_at = datetime.now(UTC) + timedelta(days=VERIFICATION_TTL_DAYS)
    verification.last_checked_at = None
    onboarding.status = "verification_pending"
    onboarding.current_step = "verification"
    onboarding.last_error_code = None
    record_security_event(
        db,
        event_type="website_onboarding.verification_file_renewed",
        result="success",
        summary="Website-verificatiebestand vernieuwd",
        actor_user_id=actor_user_id,
        client_id=onboarding.client_id,
        target_type="website_onboarding",
        target_id=onboarding.id,
        details={"method": "https_file"},
    )
    db.commit()
    return f"{VERIFICATION_PREFIX}{token}"


def start_first_onboarding_crawl(
    db: Session,
    onboarding_id: UUID,
    *,
    actor_user_id: UUID | None,
    preferences: WebsiteOnboardingCrawlPreferences,
) -> tuple[WebsiteOnboarding, CrawlJob]:
    onboarding = db.scalar(
        select(WebsiteOnboarding).where(WebsiteOnboarding.id == onboarding_id).with_for_update()
    )
    if onboarding is None:
        raise LookupError("Website onboarding not found")
    if onboarding.first_crawl_job_id is not None:
        existing_job = db.get(CrawlJob, onboarding.first_crawl_job_id)
        if existing_job is None:
            raise LookupError("First onboarding crawl not found")
        return onboarding, existing_job
    verification = _verification(db, onboarding.id, lock=True)
    if verification.status != "verified":
        raise ValueError("Verifieer eerst het website-eigendom")
    if crawl_deployment_is_active(db):
        raise RuntimeError("Crawls zijn tijdelijk gepauzeerd voor deployment")

    website = db.get(Website, onboarding.website_id)
    if website is None:
        raise LookupError("Onboarding website not found")
    website_settings = website.settings or WebsiteSettings(website_id=website.id)
    for key, value in preferences.model_dump(exclude_none=True).items():
        setattr(website_settings, key, value)
    db.add(website_settings)
    settings_snapshot = {
        "max_urls": preferences.max_urls,
        "request_delay_ms": preferences.request_delay_ms,
        "concurrency": preferences.concurrency,
        "request_timeout_seconds": website_settings.request_timeout_seconds,
        "max_response_size": website_settings.max_response_size,
        "respect_robots_txt": preferences.respect_robots_txt,
    }
    job = CrawlJob(
        website_id=website.id,
        job_type="full_site_crawl",
        settings_snapshot=settings_snapshot,
        queue_name=crawl_queue_name("full_site_crawl"),
        queue_priority=website_settings.queue_priority,
    )
    db.add(job)
    db.flush()
    onboarding.first_crawl_job_id = job.id
    onboarding.status = "crawl_queued"
    onboarding.current_step = "first_crawl"
    onboarding.last_error_code = None
    record_security_event(
        db,
        event_type="website_onboarding.first_crawl_created",
        result="success",
        summary="Eerste websitecrawl exact eenmaal aangemaakt",
        actor_user_id=actor_user_id,
        client_id=onboarding.client_id,
        target_type="crawl_job",
        target_id=job.id,
        details={"job_type": "full_site_crawl"},
    )
    db.commit()
    if get_settings().app_env != "test" and not pause_job_if_deployment_active(db, job):
        queued = enqueue_crawl_job(
            str(job.id),
            job_type=job.job_type,
            priority=job.queue_priority,
            website_id=str(job.website_id),
        )
        if queued is False:
            job.status = "waiting_for_capacity"
            db.commit()
    return onboarding, job


def check_website_ownership(
    db: Session,
    onboarding_id: UUID,
    *,
    transport: httpx.BaseTransport | None = None,
) -> tuple[WebsiteOnboarding, WebsiteOwnershipVerification]:
    onboarding = db.scalar(
        select(WebsiteOnboarding).where(WebsiteOnboarding.id == onboarding_id).with_for_update()
    )
    if onboarding is None:
        raise LookupError("Website onboarding not found")
    verification = _verification(db, onboarding.id, lock=True)
    if verification.status == "verified":
        return onboarding, verification
    now = datetime.now(UTC)
    verification.attempt_count += 1
    verification.last_checked_at = now
    if _aware(verification.expires_at) <= now:
        verification.status = "expired"
        onboarding.last_error_code = "verification_expired"
        db.commit()
        return onboarding, verification

    website = db.get(Website, onboarding.website_id)
    if website is None:
        raise LookupError("Onboarding website not found")
    target_url = _verification_url(website.base_url)
    error_code: str | None = None
    try:
        response = fetch_url(
            target_url,
            timeout_seconds=10,
            max_response_size=4096,
            max_redirects=3,
            transport=transport,
        )
        if response.status_code != 200:
            error_code = "verification_file_unavailable"
        elif not _same_origin_and_path(website.base_url, response.final_url):
            error_code = "verification_redirect_outside_scope"
        elif not _valid_file_content(response.content, verification.token_hash):
            error_code = "verification_token_mismatch"
    except CrawlError as exc:
        error_code = f"verification_{exc.error_type}"

    if error_code is None:
        verification.status = "verified"
        verification.verified_at = now
        onboarding.status = "verified"
        onboarding.current_step = "crawl_preferences"
        onboarding.last_error_code = None
        website.status = "active"
        result = "success"
    else:
        onboarding.last_error_code = error_code
        result = "failed"
    record_security_event(
        db,
        event_type="website_onboarding.ownership_checked",
        result=result,
        summary="Website-eigendomsverificatie uitgevoerd",
        actor_user_id=onboarding.started_by_user_id,
        client_id=onboarding.client_id,
        target_type="website_onboarding",
        target_id=onboarding.id,
        details={"method": "https_file", "error_code": error_code},
    )
    db.commit()
    return onboarding, verification


def _verification(
    db: Session, onboarding_id: UUID, *, lock: bool = False
) -> WebsiteOwnershipVerification:
    query = select(WebsiteOwnershipVerification).where(
        WebsiteOwnershipVerification.onboarding_id == onboarding_id
    )
    if lock:
        query = query.with_for_update()
    verification = db.scalar(query)
    if verification is None:
        raise LookupError("Website verification not found")
    return verification


def _read(
    onboarding: WebsiteOnboarding,
    verification: WebsiteOwnershipVerification,
    *,
    token: str | None = None,
    first_crawl_job: CrawlJob | None = None,
) -> WebsiteOnboardingRead:
    return WebsiteOnboardingRead(
        id=onboarding.id,
        client_id=onboarding.client_id,
        website_id=onboarding.website_id,
        status=onboarding.status,
        current_step=onboarding.current_step,
        last_error_code=onboarding.last_error_code,
        verification_status=verification.status,
        verification_path=VERIFICATION_PATH,
        verification_expires_at=verification.expires_at,
        verification_file_content=f"{VERIFICATION_PREFIX}{token}" if token else None,
        first_crawl_job_id=onboarding.first_crawl_job_id,
        first_crawl_status=first_crawl_job.status if first_crawl_job else None,
    )


def _same_origin_and_path(base_url: str, final_url: str) -> bool:
    base = urlsplit(base_url)
    final = urlsplit(final_url)
    return (
        base.scheme.lower() == final.scheme.lower()
        and base.netloc.lower() == final.netloc.lower()
        and final.path == VERIFICATION_PATH
        and not final.query
        and not final.fragment
    )


def _verification_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    return urlunsplit((parsed.scheme, parsed.netloc, VERIFICATION_PATH, "", ""))


def _valid_file_content(content: bytes, expected_hash: str) -> bool:
    try:
        value = content.decode("utf-8").strip()
    except UnicodeDecodeError:
        return False
    if not value.startswith(VERIFICATION_PREFIX):
        return False
    token = value.removeprefix(VERIFICATION_PREFIX)
    return bool(token) and secrets.compare_digest(token_hash(token), expected_hash)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)

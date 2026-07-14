from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.queue import enqueue_crawl_job
from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.models.common import utc_now
from app.models.crawl import CrawlRun
from app.models.discovery import CrawlJob, Url
from app.schemas.discovery import CrawlJobCreate, CrawlJobRead, UrlRead, UrlRegister
from app.services.authorization import require_website_access
from app.services.url_registry import register_url
from app.services.url_scope import is_url_in_website_scope

router = APIRouter(tags=["discovery"])


@router.get("/websites/{website_id}/urls", response_model=list[UrlRead])
def list_urls(
    website_id: UUID,
    active: bool | None = True,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> list[Url]:
    require_website_access(db, principal, website_id)
    query = select(Url).where(Url.website_id == website_id).order_by(Url.normalized_url)
    if active is not None:
        query = query.where(Url.is_active == active)
    return list(db.scalars(query.offset(offset).limit(limit)))


@router.post(
    "/websites/{website_id}/urls", response_model=UrlRead, status_code=status.HTTP_201_CREATED
)
def add_url(
    website_id: UUID,
    payload: UrlRegister,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> Url:
    website = require_website_access(db, principal, website_id, admin=True)
    if not is_url_in_website_scope(
        str(payload.url),
        base_url=website.base_url,
        allowed_subdomains=website.settings.allowed_subdomains,
    ):
        raise HTTPException(status_code=422, detail="URL valt buiten het ingestelde websitedomein")
    try:
        url = register_url(
            db,
            website_id=website_id,
            raw_url=payload.url,
            source_type=payload.source_type,
            source_url=payload.source_url,
            ignored_query_parameters=frozenset(website.settings.ignored_query_parameters),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    db.refresh(url)
    return url


@router.post("/crawl-jobs", response_model=CrawlJobRead, status_code=201)
def create_crawl_job(
    payload: CrawlJobCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> CrawlJob:
    website = require_website_access(db, principal, payload.website_id, admin=True)
    running = db.scalar(
        select(CrawlJob.id).where(
            CrawlJob.website_id == payload.website_id,
            CrawlJob.status.in_(["pending", "running", "pause_requested", "paused"]),
        )
    )
    if running:
        raise HTTPException(status_code=409, detail="A crawl is already pending or running")
    data = payload.model_dump()
    if not data["settings_snapshot"]:
        data["settings_snapshot"] = {
            "max_urls": website.settings.max_urls,
            "request_delay_ms": website.settings.request_delay_ms,
            "concurrency": website.settings.concurrency,
            "request_timeout_seconds": website.settings.request_timeout_seconds,
            "max_response_size": website.settings.max_response_size,
            "respect_robots_txt": website.settings.respect_robots_txt,
        }
    job = CrawlJob(**data)
    db.add(job)
    db.commit()
    db.refresh(job)
    if get_settings().app_env != "test":
        enqueue_crawl_job(str(job.id))
    return job


def _crawl_job_or_404(job_id: UUID, db: Session, principal: Principal) -> CrawlJob:
    job = db.get(CrawlJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Crawl job not found")
    require_website_access(db, principal, job.website_id, admin=True)
    return job


@router.post("/crawl-jobs/{job_id}/pause", response_model=CrawlJobRead)
def pause_crawl_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> CrawlJob:
    job = _crawl_job_or_404(job_id, db, principal)
    if job.status != "running":
        raise HTTPException(status_code=409, detail="Deze crawl kan niet worden gepauzeerd")
    job.status = "pause_requested"
    db.commit()
    db.refresh(job)
    return job


@router.post("/crawl-jobs/{job_id}/resume", response_model=CrawlJobRead)
def resume_crawl_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> CrawlJob:
    job = _crawl_job_or_404(job_id, db, principal)
    if job.status != "paused":
        raise HTTPException(status_code=409, detail="Alleen een gepauzeerde crawl kan hervatten")
    job.status = "pending"
    job.finished_at = None
    job.error_message = None
    db.commit()
    if get_settings().app_env != "test":
        enqueue_crawl_job(str(job.id), attempt=job.attempt_count + 1)
    db.refresh(job)
    return job


@router.post("/crawl-jobs/{job_id}/cancel", response_model=CrawlJobRead)
def cancel_crawl_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> CrawlJob:
    job = _crawl_job_or_404(job_id, db, principal)
    if job.status not in {"pending", "running", "pause_requested", "paused"}:
        raise HTTPException(status_code=409, detail="Deze crawl kan niet worden gestopt")
    run = db.scalar(select(CrawlRun).where(CrawlRun.crawl_job_id == job.id))
    if job.status in {"pending", "paused"}:
        finished = utc_now()
        job.status = "cancelled"
        job.finished_at = finished
        if run:
            run.status = "cancelled"
            run.finished_at = finished
    else:
        job.status = "cancel_requested"
    db.commit()
    db.refresh(job)
    return job


@router.get("/crawl-jobs/{job_id}", response_model=CrawlJobRead)
def get_crawl_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> CrawlJob:
    job = db.get(CrawlJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Crawl job not found")
    require_website_access(db, principal, job.website_id)
    return job

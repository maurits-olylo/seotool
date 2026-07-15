from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.queue import enqueue_crawl_job
from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.models.common import utc_now
from app.models.crawl import CrawlRun, UrlLink
from app.models.discovery import CrawlJob, Url
from app.schemas.discovery import CrawlJobCreate, CrawlJobRead, CrawlRouteRead, UrlRead, UrlRegister
from app.services.authorization import require_website_access
from app.services.crawl_deployment import crawl_deployment_is_active
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
) -> list[UrlRead]:
    require_website_access(db, principal, website_id)
    query = select(Url).where(Url.website_id == website_id).order_by(Url.normalized_url)
    if active is not None:
        query = query.where(Url.is_active == active)
    urls = list(db.scalars(query.offset(offset).limit(limit)))
    latest_full_run = db.scalar(
        select(CrawlRun)
        .where(CrawlRun.website_id == website_id, CrawlRun.crawl_type == "full_site_crawl")
        .order_by(CrawlRun.started_at.desc())
        .limit(1)
    )
    return [_url_read_with_depth_context(url, latest_full_run) for url in urls]


def _url_read_with_depth_context(url: Url, run: CrawlRun | None) -> UrlRead:
    data = UrlRead.model_validate(url).model_dump()
    if run is None:
        context = "Nog geen volledige crawl uitgevoerd"
        reliable = False
    elif run.status == "succeeded":
        reliable = True
        crawl_date = run.started_at.date().isoformat()
        context = (
            f"Kortste interne route uit voltooide crawl van {crawl_date}"
            if url.crawl_depth is not None
            else f"Geen interne route gevonden in voltooide crawl van {crawl_date}"
        )
    elif run.status in {"running", "pause_requested", "paused"}:
        reliable = False
        context = "Voorlopige diepte uit de lopende, nog onvoltooide crawl"
    else:
        reliable = False
        context = "Onvolledige dieptemeting: de laatste volledige crawl is niet voltooid"
    data["crawl_depth_reliable"] = reliable
    data["crawl_depth_context"] = context
    return UrlRead.model_validate(data)


@router.get("/urls/{url_id}/crawl-route", response_model=CrawlRouteRead)
def get_crawl_route(
    url_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> CrawlRouteRead:
    target = db.get(Url, url_id)
    if not target:
        raise HTTPException(status_code=404, detail="URL not found")
    require_website_access(db, principal, target.website_id)
    run = db.scalar(
        select(CrawlRun)
        .where(CrawlRun.website_id == target.website_id, CrawlRun.crawl_type == "full_site_crawl")
        .order_by(CrawlRun.started_at.desc())
        .limit(1)
    )
    context = _url_read_with_depth_context(target, run).crawl_depth_context
    if not run or run.status != "succeeded" or target.crawl_depth is None:
        return CrawlRouteRead(reliable=False, depth=target.crawl_depth, route=[], context=context)
    route = [target.normalized_url]
    current = target
    current_depth = target.crawl_depth
    while current_depth > 0:
        predecessor = db.scalar(
            select(Url)
            .join(UrlLink, UrlLink.source_url_id == Url.id)
            .where(
                UrlLink.crawl_run_id == run.id,
                UrlLink.target_url_id == current.id,
                UrlLink.is_internal.is_(True),
                Url.crawl_depth == current_depth - 1,
            )
            .order_by(Url.normalized_url)
            .limit(1)
        )
        if predecessor is None:
            return CrawlRouteRead(
                reliable=False,
                depth=target.crawl_depth,
                route=list(reversed(route)),
                context=(
                    "Diepte is bekend, maar de volledige linkroute kon niet worden gereconstrueerd"
                ),
            )
        route.append(predecessor.normalized_url)
        current = predecessor
        current_depth -= 1
    return CrawlRouteRead(
        reliable=True,
        depth=target.crawl_depth,
        route=list(reversed(route)),
        context=context,
    )


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
    if crawl_deployment_is_active(db):
        raise HTTPException(
            status_code=503, detail="Crawls zijn tijdelijk gepauzeerd voor deployment"
        )
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
    if crawl_deployment_is_active(db):
        raise HTTPException(
            status_code=503, detail="Crawls zijn tijdelijk gepauzeerd voor deployment"
        )
    if job.status not in {"paused", "failed"}:
        raise HTTPException(
            status_code=409, detail="Alleen een gepauzeerde of mislukte crawl kan hervatten"
        )
    if job.status == "failed" and not db.scalar(
        select(CrawlRun.id).where(CrawlRun.crawl_job_id == job.id)
    ):
        raise HTTPException(status_code=409, detail="Deze crawl heeft geen hervatbare voortgang")
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

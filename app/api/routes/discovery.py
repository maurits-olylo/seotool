from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.queue import crawl_queue_state, enqueue_crawl_job
from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.models.common import utc_now
from app.models.crawl import CrawlRun, UrlLink, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.issues import Issue
from app.models.website import Website
from app.schemas.discovery import CrawlJobCreate, CrawlJobRead, CrawlRouteRead, UrlRead, UrlRegister
from app.services.authorization import require_website_access
from app.services.crawl_deployment import crawl_deployment_is_active
from app.services.url_filtering import is_excluded_url
from app.services.url_normalization import NormalizationOptions, normalize_url
from app.services.url_registry import register_url
from app.services.url_scope import is_url_in_website_scope

router = APIRouter(tags=["discovery"])
ACTIVE_ISSUE_STATUSES = {
    "new",
    "review",
    "accepted",
    "planned",
    "in_progress",
    "waiting_for_client",
}
SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


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
    issue_summaries = _active_issue_summaries(db, [url.id for url in urls])
    return [
        _url_read_with_depth_context(url, latest_full_run, issue_summaries.get(url.id))
        for url in urls
    ]


def _url_read_with_depth_context(
    url: Url,
    run: CrawlRun | None,
    issue_summary: dict[str, object] | None = None,
) -> UrlRead:
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
    if issue_summary:
        data.update(issue_summary)
    return UrlRead.model_validate(data)


def _active_issue_summaries(db: Session, url_ids: list[UUID]) -> dict[UUID, dict[str, object]]:
    if not url_ids:
        return {}
    issues = list(
        db.scalars(
            select(Issue)
            .where(
                Issue.url_id.in_(url_ids),
                Issue.status.in_(ACTIVE_ISSUE_STATUSES),
            )
            .order_by(Issue.url_id, Issue.severity, Issue.title)
        )
    )
    grouped: dict[UUID, list[Issue]] = {}
    for issue in issues:
        if issue.url_id is not None:
            grouped.setdefault(issue.url_id, []).append(issue)
    return {
        url_id: {
            "active_issue_count": len(items),
            "highest_issue_severity": max(
                items,
                key=lambda item: SEVERITY_RANK.get(item.severity, 0),
            ).severity,
            "active_issue_titles": [
                item.title
                for item in sorted(
                    items,
                    key=lambda item: (
                        -SEVERITY_RANK.get(item.severity, 0),
                        item.title,
                    ),
                )
            ],
        }
        for url_id, items in grouped.items()
    }


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
    normalized = normalize_url(
        str(payload.url),
        options=NormalizationOptions(
            ignored_query_parameters=frozenset(website.settings.ignored_query_parameters)
        ),
    )
    if is_excluded_url(normalized, website.settings.excluded_url_patterns):
        raise HTTPException(status_code=422, detail="URL valt onder een uitgesloten URL-patroon")
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
) -> CrawlJobRead:
    require_website_access(db, principal, payload.website_id, admin=True)
    website = db.scalar(select(Website).where(Website.id == payload.website_id).with_for_update())
    if website is None:
        raise HTTPException(status_code=404, detail="Website not found")
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
        enqueue_crawl_job(str(job.id), job_type=job.job_type)
    return _crawl_job_read(job)


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
) -> CrawlJobRead:
    job = _crawl_job_or_404(job_id, db, principal)
    if job.status != "running":
        raise HTTPException(status_code=409, detail="Deze crawl kan niet worden gepauzeerd")
    job.status = "pause_requested"
    db.commit()
    db.refresh(job)
    return _crawl_job_read(job)


@router.post("/crawl-jobs/{job_id}/resume", response_model=CrawlJobRead)
def resume_crawl_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> CrawlJobRead:
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
        select(UrlSnapshot.id)
        .join(CrawlRun, CrawlRun.id == UrlSnapshot.crawl_run_id)
        .where(CrawlRun.crawl_job_id == job.id)
        .limit(1)
    ):
        raise HTTPException(status_code=409, detail="Deze crawl heeft geen hervatbare voortgang")
    db.scalar(select(Website.id).where(Website.id == job.website_id).with_for_update())
    competing = db.scalar(
        select(CrawlJob.id).where(
            CrawlJob.website_id == job.website_id,
            CrawlJob.id != job.id,
            CrawlJob.status.in_(["pending", "running", "pause_requested", "paused"]),
        )
    )
    if competing:
        raise HTTPException(
            status_code=409,
            detail="Er staat al een andere crawl voor deze website",
        )
    job.status = "pending"
    job.finished_at = None
    job.error_message = None
    db.commit()
    if get_settings().app_env != "test":
        enqueue_crawl_job(
            str(job.id),
            job_type=job.job_type,
            attempt=job.attempt_count + 1,
        )
    db.refresh(job)
    return _crawl_job_read(job)


@router.post("/crawl-jobs/{job_id}/cancel", response_model=CrawlJobRead)
def cancel_crawl_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> CrawlJobRead:
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
    return _crawl_job_read(job)


@router.get("/crawl-jobs/{job_id}", response_model=CrawlJobRead)
def get_crawl_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> CrawlJobRead:
    job = db.get(CrawlJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Crawl job not found")
    require_website_access(db, principal, job.website_id)
    return _crawl_job_read(job)


@router.get("/websites/{website_id}/crawl-jobs/active", response_model=CrawlJobRead | None)
def get_active_crawl_job(
    website_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> CrawlJobRead | None:
    require_website_access(db, principal, website_id)
    job = db.scalar(
        select(CrawlJob)
        .where(
            CrawlJob.website_id == website_id,
            CrawlJob.status.in_(
                ["pending", "running", "pause_requested", "paused", "cancel_requested"]
            ),
        )
        .order_by(CrawlJob.created_at.desc())
        .limit(1)
    )
    return _crawl_job_read(job) if job else None


def _crawl_job_read(job: CrawlJob) -> CrawlJobRead:
    data = CrawlJobRead.model_validate(job).model_dump()
    if get_settings().app_env != "test":
        try:
            queue = crawl_queue_state(str(job.id), job_type=job.job_type)
        except Exception:
            pass
        else:
            data.update(
                queue_position=queue.position,
                queue_depth=queue.queued_jobs,
                worker_capacity=queue.workers,
            )
    return CrawlJobRead.model_validate(data)

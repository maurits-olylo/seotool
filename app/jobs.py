import time
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select, update

from app.db.session import SessionLocal
from app.models.common import utc_now
from app.models.crawl import CrawlRun, UrlLink, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.website import Website
from app.services.http_crawler import CrawlError, fetch_url
from app.services.internal_link_analysis import detect_orphan_pages
from app.services.sitemap import parse_sitemap
from app.services.snapshot import store_fetch_result
from app.services.url_registry import register_url

logger = structlog.get_logger()


def execute_crawl_job(job_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(CrawlJob, uuid.UUID(job_id))
        if job is None or job.status == "cancelled":
            return
        running = db.scalar(
            select(CrawlJob.id).where(
                CrawlJob.website_id == job.website_id,
                CrawlJob.status == "running",
                CrawlJob.id != job.id,
            )
        )
        if running:
            raise RuntimeError("Another crawl is already running for this website")
        job.status = "running"
        job.started_at = utc_now()
        job.attempt_count += 1
        run = CrawlRun(
            crawl_job_id=job.id,
            website_id=job.website_id,
            crawl_type=job.job_type,
        )
        db.add(run)
        db.commit()
        try:
            if job.job_type in {"fetch_sitemap", "full_site_crawl"}:
                _import_sitemaps(db, job, run)
            if job.job_type == "fetch_sitemap":
                run.status = "succeeded"
                job.status = "succeeded"
                return
            if job.job_type == "full_site_crawl":
                _crawl_full_site(db, job, run)
                run.status = "succeeded" if run.failed_urls == 0 else "partially_succeeded"
                job.status = run.status
                return
            urls = list(
                db.scalars(
                    select(Url)
                    .where(Url.website_id == job.website_id, Url.is_active.is_(True))
                    .order_by(Url.normalized_url)
                    .limit(int(job.settings_snapshot.get("max_urls", 10_000)))
                )
            )
            run.discovered_urls = len(urls)
            for url in urls:
                _crawl_one(db, job, run, url)
                _respect_request_delay(job)
            run.status = "succeeded" if run.failed_urls == 0 else "partially_succeeded"
            job.status = run.status
        except Exception as exc:
            db.rollback()
            job = db.get(CrawlJob, uuid.UUID(job_id))
            run = (
                db.scalar(select(CrawlRun).where(CrawlRun.crawl_job_id == job.id)) if job else None
            )
            if job:
                job.status = "failed"
                job.error_message = str(exc)[:4000]
            if run:
                run.status = "failed"
            logger.exception("crawl_job_failed", job_id=job_id)
            raise
        finally:
            finished = datetime.now(UTC)
            if job:
                job.finished_at = finished
            if run:
                run.finished_at = finished
            db.commit()


def _import_sitemaps(db, job: CrawlJob, run: CrawlRun) -> None:  # type: ignore[no-untyped-def]
    website = db.get(Website, job.website_id)
    if website is None:
        raise RuntimeError("Website does not exist")
    pending = list(website.settings.sitemap_urls)
    visited: set[str] = set()
    while pending and len(visited) < 100:
        sitemap_url = pending.pop(0)
        if sitemap_url in visited:
            continue
        visited.add(sitemap_url)
        result = fetch_url(
            sitemap_url,
            timeout_seconds=website.settings.request_timeout_seconds,
            max_response_size=website.settings.max_response_size,
        )
        document = parse_sitemap(result.content)
        pending.extend(document.child_sitemaps)
        for item in document.urls[: website.settings.max_urls]:
            register_url(
                db,
                website_id=website.id,
                raw_url=item.location,
                source_type="sitemap",
                source_url=sitemap_url,
                ignored_query_parameters=frozenset(website.settings.ignored_query_parameters),
            )
            run.discovered_urls += 1
        db.commit()


def _crawl_full_site(db, job: CrawlJob, run: CrawlRun) -> None:  # type: ignore[no-untyped-def]
    website = db.get(Website, job.website_id)
    if website is None:
        raise RuntimeError("Website does not exist")
    db.execute(update(Url).where(Url.website_id == website.id).values(crawl_depth=None))
    root = register_url(
        db,
        website_id=website.id,
        raw_url=website.base_url,
        source_type="known",
        source_url="",
        ignored_query_parameters=frozenset(website.settings.ignored_query_parameters),
    )
    root.crawl_depth = 0
    db.commit()

    pending: list[tuple[uuid.UUID, int]] = [(root.id, 0)]
    visited: set[uuid.UUID] = set()
    maximum = int(job.settings_snapshot.get("max_urls", website.settings.max_urls))
    while pending and len(visited) < maximum:
        url_id, depth = pending.pop(0)
        if url_id in visited:
            continue
        url = db.get(Url, url_id)
        if url is None or not url.is_active:
            continue
        url.crawl_depth = depth
        visited.add(url.id)
        _crawl_one(db, job, run, url)
        _respect_request_delay(job)
        discovered = list(
            db.scalars(
                select(Url)
                .join(UrlLink, UrlLink.target_url_id == Url.id)
                .where(
                    UrlLink.crawl_run_id == run.id,
                    UrlLink.source_url_id == url.id,
                    UrlLink.is_internal.is_(True),
                )
                .order_by(Url.normalized_url)
            )
        )
        for target in discovered:
            next_depth = depth + 1
            if target.crawl_depth is None or next_depth < target.crawl_depth:
                target.crawl_depth = next_depth
            if target.id not in visited:
                pending.append((target.id, next_depth))
        db.commit()
    run.discovered_urls = len(visited)
    detect_orphan_pages(
        db,
        website_id=website.id,
        crawl_run_id=run.id,
    )
    db.commit()


def _respect_request_delay(job: CrawlJob) -> None:
    delay_ms = max(0, int(job.settings_snapshot.get("request_delay_ms", 0)))
    if delay_ms:
        time.sleep(delay_ms / 1000)


def _crawl_one(db, job: CrawlJob, run: CrawlRun, url: Url) -> None:  # type: ignore[no-untyped-def]
    settings = job.settings_snapshot
    try:
        result = fetch_url(
            url.normalized_url,
            timeout_seconds=int(settings.get("request_timeout_seconds", 20)),
            max_response_size=int(settings.get("max_response_size", 5_000_000)),
        )
        store_fetch_result(db, url=url, crawl_run_id=run.id, result=result)
        run.crawled_urls += 1
        db.commit()
    except CrawlError as exc:
        db.add(
            UrlSnapshot(
                url_id=url.id,
                crawl_run_id=run.id,
                requested_url=url.normalized_url,
                error_message=str(exc),
                is_indexable=False,
            )
        )
        run.failed_urls += 1
        db.commit()

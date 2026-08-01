import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urljoin

import structlog
from sqlalchemy import select, update

from app.db.session import SessionLocal
from app.models.common import utc_now
from app.models.crawl import CrawlRun, UrlLink, UrlSnapshot
from app.models.discovery import CrawlJob, Url, UrlSource
from app.models.website import Website
from app.services.analysis import analyze_snapshot
from app.services.asset_checks import ASSET_ISSUE_TYPES, HTML_ONLY_ISSUE_TYPES, inspect_asset
from app.services.asset_quality_analysis import analyze_asset_quality
from app.services.content_similarity import detect_duplicate_content
from app.services.contextual_404 import classify_404_issues
from app.services.crawl_deployment import pause_job_if_deployment_active
from app.services.element_locations import mark_target_elements
from app.services.http_crawler import CrawlError, fetch_metadata, fetch_url
from app.services.indexation_analysis import analyze_indexation_consistency
from app.services.internal_link_analysis import analyze_internal_link_quality, detect_orphan_pages
from app.services.internal_redirect_analysis import analyze_internal_redirect_patterns
from app.services.issue_engine import reconcile_issues
from app.services.job_identifier_analysis import analyze_job_identifier_risk
from app.services.pagination_analysis import analyze_pagination_series
from app.services.retention_operations import create_retention_operation
from app.services.robots import RobotsRules
from app.services.server_error_analysis import analyze_server_error_incident
from app.services.sitemap import InvalidSitemapError, parse_sitemap
from app.services.sitemap_redirect_analysis import analyze_sitemap_redirect_patterns
from app.services.snapshot import store_fetch_result
from app.services.structured_data_analysis import analyze_breadcrumb_consistency
from app.services.technical_checks import (
    CRAWL_ERROR_ISSUE_TYPES,
    IssueSignal,
    inspect_crawl_error,
)
from app.services.template_issue_analysis import analyze_template_issue_clusters
from app.services.thin_content_analysis import analyze_contextual_thin_content
from app.services.url_filtering import (
    MAX_QUERY_VARIANTS_PER_PATH,
    is_excluded_url,
    is_probable_html_page,
    query_variant_group,
)
from app.services.url_normalization import NormalizationOptions, normalize_url
from app.services.url_registry import register_url
from app.services.url_scope import is_url_in_website_scope

logger = structlog.get_logger()
CRAWL_HEARTBEAT_INTERVAL_SECONDS = 15
MAX_SITEMAP_DOCUMENTS = 1_000


@dataclass(frozen=True)
class SitemapImportResult:
    documents: int
    urls: int
    complete: bool
    remaining_documents: int = 0


class CrawlPaused(RuntimeError):
    pass


class CrawlCancelled(RuntimeError):
    pass


def execute_crawl_job(job_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(CrawlJob, uuid.UUID(job_id))
        if job is None or job.status in {"cancelled", "paused", "pause_requested"}:
            return
        if pause_job_if_deployment_active(db, job):
            logger.info("crawl_job_paused_for_deployment", job_id=job_id)
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
        existing_run = db.scalar(select(CrawlRun).where(CrawlRun.crawl_job_id == job.id))
        resumed = existing_run is not None
        job.status = "running"
        job.started_at = job.started_at or utc_now()
        job.attempt_count += 1
        run = existing_run or CrawlRun(
            crawl_job_id=job.id, website_id=job.website_id, crawl_type=job.job_type
        )
        run.status = "running"
        run.phase = "url_check"
        run.phase_current = 0
        run.phase_total = 0
        run.heartbeat_at = utc_now()
        db.add(run)
        db.commit()
        sitemap_import_complete = True
        try:
            website = db.get(Website, job.website_id)
            if website is None:
                raise RuntimeError("Website does not exist")
            if job.job_type == "recalculate_issues":
                _recalculate_stored_issues(db, job, run)
                run.status = "succeeded"
                job.status = "succeeded"
                return
            _deactivate_out_of_scope_urls(db, website)
            db.commit()
            if job.job_type == "fetch_sitemap":
                sitemap_import = _import_sitemaps(db, job, run)
            elif job.job_type == "full_site_crawl" and not resumed:
                sitemap_import_complete = _import_sitemaps(db, job, run).complete
            if job.job_type == "fetch_sitemap":
                run.crawled_urls = sitemap_import.documents
                if sitemap_import.documents == 0:
                    message = "Geen sitemap ingesteld of gevonden via robots.txt en /sitemap.xml"
                    run.status = "failed"
                    job.status = "failed"
                    job.error_message = message
                elif not sitemap_import.complete:
                    message = (
                        f"Sitemapimport afgebroken na {sitemap_import.documents} documenten; "
                        f"nog niet verwerkt: {sitemap_import.remaining_documents}"
                    )
                    run.discovered_urls = sitemap_import.urls
                    run.status = "partially_succeeded"
                    job.status = "partially_succeeded"
                    job.error_message = message
                else:
                    run.discovered_urls = sitemap_import.urls
                    run.status = "succeeded"
                    job.status = "succeeded"
                return
            if job.job_type == "full_site_crawl":
                site_crawl_complete = _crawl_full_site(db, job, run, resumed=resumed)
                _check_crawl_control(db, job, run)
                _set_crawl_phase(db, run, "404_analysis")
                classify_404_issues(
                    db,
                    website_id=job.website_id,
                    crawl_run_id=run.id,
                    check_control=lambda: _check_crawl_control(db, job, run),
                )
                _set_crawl_phase(db, run, "finalizing")
                run.status = (
                    "succeeded"
                    if run.failed_urls == 0 and site_crawl_complete and sitemap_import_complete
                    else "partially_succeeded"
                )
                job.status = run.status
                return
            robots = _load_robots_rules(db, job)
            urls = list(
                db.scalars(
                    select(Url)
                    .where(Url.website_id == job.website_id, Url.is_active.is_(True))
                    .order_by(Url.normalized_url)
                    .limit(int(job.settings_snapshot.get("max_urls", 10_000)))
                )
            )
            candidate_count = len(urls)
            urls = _limit_query_variants(urls, website_id=website.id)
            run.skipped_urls += candidate_count - len(urls)
            run.discovered_urls = len(urls)
            run.phase_total = len(urls)
            completed_url_ids = set(
                db.scalars(select(UrlSnapshot.url_id).where(UrlSnapshot.crawl_run_id == run.id))
            )
            for url in urls:
                if url.id in completed_url_ids:
                    run.phase_current += 1
                    continue
                _check_crawl_control(db, job, run)
                if is_probable_html_page(url.normalized_url):
                    _crawl_one(db, job, run, url, robots=robots)
                else:
                    _audit_asset(db, job, run, url)
                run.phase_current += 1
                run.heartbeat_at = utc_now()
                _respect_request_delay(job)
            _set_crawl_phase(db, run, "404_analysis")
            classify_404_issues(
                db,
                website_id=job.website_id,
                crawl_run_id=run.id,
                check_control=lambda: _check_crawl_control(db, job, run),
            )
            _set_crawl_phase(db, run, "internal_link_analysis")
            _check_crawl_control(db, job, run, force_heartbeat=True)
            _set_crawl_phase(db, run, "finalizing")
            run.status = "succeeded" if run.failed_urls == 0 else "partially_succeeded"
            job.status = run.status
        except CrawlPaused:
            logger.info("crawl_job_paused", job_id=job_id)
        except CrawlCancelled:
            logger.info("crawl_job_cancelled", job_id=job_id)
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
            if job and job.status != "paused":
                job.finished_at = finished
            if run and run.status != "paused":
                run.finished_at = finished
            db.commit()
            if (
                run
                and run.crawl_type == "full_site_crawl"
                and run.status in {"succeeded", "partially_succeeded"}
            ):
                try:
                    create_retention_operation(db, run.id)
                except Exception:
                    logger.exception(
                        "retention_operation_creation_failed",
                        job_id=job_id,
                        crawl_run_id=str(run.id),
                        website_id=str(run.website_id),
                    )


def _import_sitemaps(db, job: CrawlJob, run: CrawlRun) -> SitemapImportResult:  # type: ignore[no-untyped-def]
    website = db.get(Website, job.website_id)
    if website is None:
        raise RuntimeError("Website does not exist")
    configured = list(website.settings.sitemap_urls)
    robots = _load_robots_rules(db, job)
    robots_sitemaps = list(robots.sitemaps()) if robots else []
    pending = list(dict.fromkeys([*configured, *robots_sitemaps]))
    fallback_url = urljoin(website.base_url, "/sitemap.xml")
    fallback_only = not pending
    if fallback_only:
        pending.append(fallback_url)
    queued = set(pending)
    visited: set[str] = set()
    successful_roots: list[str] = []
    registered_url_ids: set[object] = set()
    while pending and len(visited) < MAX_SITEMAP_DOCUMENTS:
        sitemap_url = pending.pop(0)
        if sitemap_url in visited:
            continue
        visited.add(sitemap_url)
        try:
            result = fetch_url(
                sitemap_url,
                timeout_seconds=website.settings.request_timeout_seconds,
                max_response_size=website.settings.max_response_size,
            )
            if result.status_code != 200:
                raise InvalidSitemapError(f"Sitemap geeft HTTP {result.status_code}")
            document = parse_sitemap(result.content)
        except (CrawlError, InvalidSitemapError):
            if fallback_only and sitemap_url == fallback_url:
                logger.info(
                    "sitemap_fallback_not_found",
                    website_id=str(website.id),
                    sitemap_url=sitemap_url,
                )
                continue
            raise
        if (
            sitemap_url in configured
            or sitemap_url in robots_sitemaps
            or sitemap_url == fallback_url
        ):
            successful_roots.append(sitemap_url)
        for child in document.child_sitemaps:
            if child in queued or not is_url_in_website_scope(
                child,
                base_url=website.base_url,
                allowed_subdomains=website.settings.allowed_subdomains,
            ):
                continue
            pending.append(child)
            queued.add(child)
        for item in document.urls[: website.settings.max_urls]:
            if not is_url_in_website_scope(
                item.location,
                base_url=website.base_url,
                allowed_subdomains=website.settings.allowed_subdomains,
            ):
                logger.info(
                    "sitemap_url_outside_website_scope",
                    website_id=str(website.id),
                    sitemap_url=sitemap_url,
                    url=item.location,
                )
                continue
            normalized_item = normalize_url(
                item.location,
                options=NormalizationOptions(
                    ignored_query_parameters=frozenset(website.settings.ignored_query_parameters)
                ),
            )
            if is_excluded_url(normalized_item, website.settings.excluded_url_patterns):
                logger.info(
                    "sitemap_url_excluded",
                    website_id=str(website.id),
                    sitemap_url=sitemap_url,
                    url=normalized_item,
                )
                continue
            registered = register_url(
                db,
                website_id=website.id,
                raw_url=item.location,
                source_type="sitemap",
                source_url=sitemap_url,
                ignored_query_parameters=frozenset(website.settings.ignored_query_parameters),
            )
            registered_url_ids.add(registered.id)
        db.commit()
    if successful_roots:
        website.settings.sitemap_urls = list(dict.fromkeys(successful_roots))
    run.discovered_urls = len(registered_url_ids)
    db.commit()
    documents = len(visited) if successful_roots else 0
    return SitemapImportResult(
        documents=documents,
        urls=len(registered_url_ids),
        complete=not pending,
        remaining_documents=len(pending),
    )


def _crawl_full_site(  # type: ignore[no-untyped-def]
    db, job: CrawlJob, run: CrawlRun, *, resumed: bool = False
) -> bool:
    website = db.get(Website, job.website_id)
    if website is None:
        raise RuntimeError("Website does not exist")
    if not resumed:
        db.execute(update(Url).where(Url.website_id == website.id).values(crawl_depth=None))
    root = register_url(
        db,
        website_id=website.id,
        raw_url=website.base_url,
        source_type="known",
        source_url="",
        ignored_query_parameters=frozenset(website.settings.ignored_query_parameters),
    )
    if not resumed:
        root.crawl_depth = 0
    db.commit()
    robots = _load_robots_rules(db, job)

    snapshot_url_ids = set(
        db.scalars(select(UrlSnapshot.url_id).where(UrlSnapshot.crawl_run_id == run.id))
    )
    visited = {
        item.id
        for item in db.scalars(select(Url).where(Url.id.in_(snapshot_url_ids)))
        if is_probable_html_page(item.normalized_url)
    }
    eligible_urls = [
        item
        for item in db.scalars(
            select(Url)
            .where(Url.website_id == website.id, Url.is_active.is_(True))
            .order_by(Url.normalized_url)
        )
        if is_probable_html_page(item.normalized_url)
        and not is_excluded_url(
            item.normalized_url,
            website.settings.excluded_url_patterns,
        )
    ]
    eligible_count = len(eligible_urls)
    eligible_urls = _limit_query_variants(eligible_urls, website_id=website.id)
    run.skipped_urls += eligible_count - len(eligible_urls)
    query_variant_counts: dict[tuple[str, str, str], int] = {}
    for eligible_url in eligible_urls:
        group = query_variant_group(eligible_url.normalized_url)
        if group is not None:
            query_variant_counts[group] = query_variant_counts.get(group, 0) + 1
    pending = [(item.id, item.crawl_depth) for item in eligible_urls if item.id not in visited]
    pending_ids = {url_id for url_id, _depth in pending}
    frontier_ids = visited | pending_ids
    audited_assets = {
        item.id
        for item in db.scalars(select(Url).where(Url.id.in_(snapshot_url_ids)))
        if not is_probable_html_page(item.normalized_url)
    }
    maximum = int(job.settings_snapshot.get("max_urls", website.settings.max_urls))
    while pending and len(visited) < maximum:
        run.phase = "url_check"
        run.phase_current = len(visited)
        run.phase_total = min(maximum, len(frontier_ids))
        run.heartbeat_at = utc_now()
        _check_crawl_control(db, job, run)
        # Process URLs reached from the root before sitemap-only and previously known
        # seeds. This preserves breadth-first crawl depth while still auditing every
        # active URL source in the same full-site crawl.
        pending.sort(key=lambda item: (item[1] is None, item[1] or 0))
        url_id, depth = pending.pop(0)
        pending_ids.discard(url_id)
        if url_id in visited:
            continue
        url = db.get(Url, url_id)
        if url is None or not url.is_active:
            continue
        if depth is not None:
            depth = min(depth, url.crawl_depth) if url.crawl_depth is not None else depth
            url.crawl_depth = depth
        visited.add(url.id)
        run.discovered_urls = len(frontier_ids)
        _crawl_one(db, job, run, url, robots=robots)
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
        discovered_by_source = list(
            db.scalars(
                select(Url)
                .join(UrlSource, UrlSource.url_id == Url.id)
                .where(
                    Url.website_id == website.id,
                    UrlSource.source_type == "internal_link",
                    UrlSource.source_url == url.normalized_url,
                )
                .order_by(Url.normalized_url)
            )
        )
        discovered = list({item.id: item for item in [*discovered, *discovered_by_source]}.values())
        for target in discovered:
            group = query_variant_group(target.normalized_url)
            is_new_frontier_url = target.id not in frontier_ids
            if (
                group is not None
                and is_new_frontier_url
                and query_variant_counts.get(group, 0) >= MAX_QUERY_VARIANTS_PER_PATH
            ):
                run.skipped_urls += 1
                continue
            if not is_probable_html_page(target.normalized_url):
                if target.id not in audited_assets:
                    _audit_asset(db, job, run, target)
                    audited_assets.add(target.id)
                    _respect_request_delay(job)
                continue
            next_depth = depth + 1 if depth is not None else None
            if next_depth is not None and (
                target.crawl_depth is None or next_depth < target.crawl_depth
            ):
                target.crawl_depth = next_depth
            frontier_ids.add(target.id)
            if group is not None and is_new_frontier_url:
                query_variant_counts[group] = query_variant_counts.get(group, 0) + 1
            if target.id not in visited and target.id not in pending_ids:
                pending.append((target.id, next_depth))
                pending_ids.add(target.id)
        db.commit()
    run.discovered_urls = len(frontier_ids)
    complete = not pending
    if complete:
        _analyze_stored_site_results(db, job=job, progress_run=run, source_run=run)
    db.commit()
    return complete


def _recalculate_stored_issues(db, job: CrawlJob, run: CrawlRun) -> None:  # type: ignore[no-untyped-def]
    source_run = db.scalar(
        select(CrawlRun)
        .where(
            CrawlRun.website_id == job.website_id,
            CrawlRun.crawl_type == "full_site_crawl",
            CrawlRun.status.in_(["succeeded", "partially_succeeded"]),
        )
        .order_by(CrawlRun.started_at.desc())
        .limit(1)
    )
    if source_run is None:
        raise RuntimeError("Geen afgeronde volledige crawl beschikbaar voor herberekening")
    run.discovered_urls = source_run.discovered_urls
    run.crawled_urls = source_run.crawled_urls
    run.html_urls = source_run.html_urls
    run.asset_urls = source_run.asset_urls
    run.skipped_urls = source_run.skipped_urls
    run.failed_urls = source_run.failed_urls
    snapshots = list(
        db.scalars(
            select(UrlSnapshot)
            .where(UrlSnapshot.crawl_run_id == source_run.id)
            .order_by(UrlSnapshot.checked_at)
        )
    )
    run.phase = "issue_recalculation"
    run.phase_current = 0
    run.phase_total = len(snapshots)
    for index, snapshot in enumerate(snapshots, start=1):
        analyze_snapshot(db, snapshot, detect_changes=False)
        run.phase_current = index
        if index % 100 == 0:
            _check_crawl_control(db, job, run, force_heartbeat=True)
            db.commit()
    _analyze_stored_site_results(db, job=job, progress_run=run, source_run=source_run)
    _set_crawl_phase(db, run, "404_analysis")
    classify_404_issues(
        db,
        website_id=job.website_id,
        crawl_run_id=source_run.id,
        check_control=lambda: _check_crawl_control(db, job, run),
    )
    _set_crawl_phase(db, run, "finalizing")


def _analyze_stored_site_results(
    db,  # type: ignore[no-untyped-def]
    *,
    job: CrawlJob,
    progress_run: CrawlRun,
    source_run: CrawlRun,
) -> None:
    website_id = job.website_id
    crawl_run_id = source_run.id
    _set_crawl_phase(db, progress_run, "internal_link_analysis")
    _check_crawl_control(db, job, progress_run)
    detect_orphan_pages(db, website_id=website_id, crawl_run_id=crawl_run_id)
    _check_crawl_control(db, job, progress_run)
    analyze_internal_link_quality(
        db,
        website_id=website_id,
        crawl_run_id=crawl_run_id,
        check_control=lambda: _check_crawl_control(db, job, progress_run),
    )
    _check_crawl_control(db, job, progress_run)
    analyze_internal_redirect_patterns(db, website_id=website_id, crawl_run_id=crawl_run_id)
    _check_crawl_control(db, job, progress_run)
    analyze_indexation_consistency(db, website_id=website_id, crawl_run_id=crawl_run_id)
    _check_crawl_control(db, job, progress_run)
    analyze_sitemap_redirect_patterns(db, website_id=website_id, crawl_run_id=crawl_run_id)
    _check_crawl_control(db, job, progress_run)
    analyze_server_error_incident(db, website_id=website_id, crawl_run_id=crawl_run_id)
    _check_crawl_control(db, job, progress_run)
    analyze_breadcrumb_consistency(db, website_id=website_id, crawl_run_id=crawl_run_id)
    _check_crawl_control(db, job, progress_run)
    detect_duplicate_content(db, website_id=website_id, crawl_run_id=crawl_run_id)
    _check_crawl_control(db, job, progress_run)
    analyze_job_identifier_risk(db, website_id=website_id, crawl_run_id=crawl_run_id)
    _check_crawl_control(db, job, progress_run)
    analyze_pagination_series(db, website_id=website_id, crawl_run_id=crawl_run_id)
    _check_crawl_control(db, job, progress_run)
    analyze_contextual_thin_content(db, website_id=website_id, crawl_run_id=crawl_run_id)
    _check_crawl_control(db, job, progress_run)
    analyze_asset_quality(db, website_id=website_id, crawl_run_id=crawl_run_id)
    _check_crawl_control(db, job, progress_run)
    analyze_template_issue_clusters(db, website_id=website_id, crawl_run_id=crawl_run_id)


def _check_crawl_control(  # type: ignore[no-untyped-def]
    db, job: CrawlJob, run: CrawlRun, *, force_heartbeat: bool = False
) -> None:
    db.refresh(job)
    if job.status == "pause_requested":
        job.status = "paused"
        run.status = "paused"
        db.commit()
        raise CrawlPaused
    if job.status in {"cancel_requested", "cancelled"}:
        finished = utc_now()
        job.status = "cancelled"
        job.finished_at = finished
        run.status = "cancelled"
        run.finished_at = finished
        db.commit()
        raise CrawlCancelled
    now = utc_now()
    heartbeat_due = (
        force_heartbeat
        or run.heartbeat_at is None
        or (now - run.heartbeat_at).total_seconds() >= CRAWL_HEARTBEAT_INTERVAL_SECONDS
    )
    if heartbeat_due:
        run.heartbeat_at = now
        db.commit()


def _set_crawl_phase(db, run: CrawlRun, phase: str, *, current: int = 0, total: int = 0) -> None:  # type: ignore[no-untyped-def]
    run.phase = phase
    run.phase_current = current
    run.phase_total = total
    run.heartbeat_at = utc_now()
    db.commit()


def _deactivate_out_of_scope_urls(db, website: Website) -> None:  # type: ignore[no-untyped-def]
    known_urls = list(db.scalars(select(Url).where(Url.website_id == website.id)))
    for known_url in known_urls:
        normalized_with_current_settings = normalize_url(
            known_url.normalized_url,
            options=NormalizationOptions(
                ignored_query_parameters=frozenset(website.settings.ignored_query_parameters)
            ),
        )
        if (
            not is_url_in_website_scope(
                known_url.normalized_url,
                base_url=website.base_url,
                allowed_subdomains=website.settings.allowed_subdomains,
            )
            or is_excluded_url(
                normalized_with_current_settings,
                website.settings.excluded_url_patterns,
            )
            or normalized_with_current_settings != known_url.normalized_url
        ):
            known_url.is_active = False


def _limit_query_variants(
    urls: list[Url],
    *,
    website_id: object,
    maximum_per_path: int | None = None,
) -> list[Url]:
    maximum_per_path = maximum_per_path or MAX_QUERY_VARIANTS_PER_PATH
    admitted: list[Url] = []
    counts: dict[tuple[str, str, str], int] = {}
    skipped = 0
    for url in urls:
        group = query_variant_group(url.normalized_url)
        if group is None:
            admitted.append(url)
            continue
        count = counts.get(group, 0)
        if count >= maximum_per_path:
            skipped += 1
            continue
        counts[group] = count + 1
        admitted.append(url)
    if skipped:
        logger.warning(
            "crawl_query_variants_limited",
            website_id=str(website_id),
            maximum_per_path=maximum_per_path,
            skipped_urls=skipped,
        )
    return admitted


def _audit_asset(db, job: CrawlJob, run: CrawlRun, url: Url) -> None:  # type: ignore[no-untyped-def]
    try:
        result = fetch_metadata(
            url.normalized_url,
            timeout_seconds=int(job.settings_snapshot.get("request_timeout_seconds", 20)),
        )
        content_length = result.headers.get("content-length")
        response_size = int(content_length) if content_length and content_length.isdigit() else None
        snapshot = UrlSnapshot(
            url_id=url.id,
            crawl_run_id=run.id,
            requested_url=result.requested_url,
            final_url=result.final_url,
            status_code=result.status_code,
            redirect_chain=result.redirect_chain,
            content_type=result.headers.get("content-type"),
            response_time_ms=result.response_time_ms,
            response_size=response_size,
            etag=result.headers.get("etag"),
            last_modified=result.headers.get("last-modified"),
            is_indexable=False,
        )
        db.add(snapshot)
        db.flush()
        run.asset_urls += 1
        asset_signals = inspect_asset(
            result.final_url,
            response_size,
            result.status_code,
            content_type=result.headers.get("content-type"),
        )
        if any(signal.issue_type == "broken_image" for signal in asset_signals):
            mark_target_elements(
                db,
                crawl_run_id=run.id,
                target_url=url.normalized_url,
                issue_type="broken_image",
                element_types={"img"},
            )
        reconcile_issues(
            db,
            website_id=job.website_id,
            url_id=url.id,
            crawl_run_id=run.id,
            snapshot_id=snapshot.id,
            signals=asset_signals,
            checked_issue_types=ASSET_ISSUE_TYPES | HTML_ONLY_ISSUE_TYPES,
        )
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


def _respect_request_delay(job: CrawlJob) -> None:
    delay_ms = max(0, int(job.settings_snapshot.get("request_delay_ms", 0)))
    if delay_ms:
        time.sleep(delay_ms / 1000)


def _crawl_one(  # type: ignore[no-untyped-def]
    db,
    job: CrawlJob,
    run: CrawlRun,
    url: Url,
    *,
    robots: RobotsRules | None = None,
) -> None:
    settings = job.settings_snapshot
    if robots and not robots.allows(url.normalized_url):
        snapshot = UrlSnapshot(
            url_id=url.id,
            crawl_run_id=run.id,
            requested_url=url.normalized_url,
            error_message="Blocked by robots.txt",
            is_indexable=False,
        )
        db.add(snapshot)
        db.flush()
        reconcile_issues(
            db,
            website_id=url.website_id,
            url_id=url.id,
            crawl_run_id=run.id,
            snapshot_id=snapshot.id,
            signals=[
                IssueSignal(
                    issue_type="robots_txt_blocked",
                    category="indexation",
                    severity="medium",
                    title="URL geblokkeerd door robots.txt",
                    description="De crawler mag deze bekende URL niet ophalen.",
                    recommended_action=(
                        "Controleer of deze robots.txt-blokkade voor de URL bewust is."
                    ),
                    evidence={"url": url.normalized_url},
                )
            ],
            checked_issue_types={"robots_txt_blocked"},
        )
        run.skipped_urls += 1
        db.commit()
        return
    try:
        result = fetch_url(
            url.normalized_url,
            timeout_seconds=int(settings.get("request_timeout_seconds", 20)),
            max_response_size=int(settings.get("max_response_size", 5_000_000)),
        )
        snapshot = store_fetch_result(db, url=url, crawl_run_id=run.id, result=result)
        run.crawled_urls += 1
        content_type = snapshot.content_type or ""
        if content_type in {"text/html", "application/xhtml+xml"}:
            run.html_urls += 1
        else:
            run.asset_urls += 1
            reconcile_issues(
                db,
                website_id=url.website_id,
                url_id=url.id,
                crawl_run_id=run.id,
                snapshot_id=snapshot.id,
                signals=inspect_asset(
                    result.final_url,
                    snapshot.response_size,
                    result.status_code,
                    content_type=content_type,
                ),
                checked_issue_types=ASSET_ISSUE_TYPES | HTML_ONLY_ISSUE_TYPES,
            )
        db.commit()
    except CrawlError as exc:
        snapshot = UrlSnapshot(
            url_id=url.id,
            crawl_run_id=run.id,
            requested_url=url.normalized_url,
            error_message=str(exc),
            is_indexable=False,
        )
        db.add(snapshot)
        db.flush()
        reconcile_issues(
            db,
            website_id=url.website_id,
            url_id=url.id,
            crawl_run_id=run.id,
            snapshot_id=snapshot.id,
            signals=inspect_crawl_error(exc),
            checked_issue_types=CRAWL_ERROR_ISSUE_TYPES,
        )
        run.failed_urls += 1
        db.commit()
    except Exception as exc:
        logger.exception(
            "crawl_url_failed_unexpectedly",
            job_id=str(job.id),
            crawl_run_id=str(run.id),
            website_id=str(url.website_id),
            url=url.normalized_url,
        )
        raise RuntimeError(f"Crawl failed for {url.normalized_url}: {exc}") from exc


def _load_robots_rules(db, job: CrawlJob) -> RobotsRules | None:  # type: ignore[no-untyped-def]
    if not bool(job.settings_snapshot.get("respect_robots_txt", True)):
        return None
    website = db.get(Website, job.website_id)
    if website is None:
        raise RuntimeError("Website does not exist")
    robots_url = urljoin(website.base_url, "/robots.txt")
    try:
        result = fetch_url(
            robots_url,
            timeout_seconds=int(job.settings_snapshot.get("request_timeout_seconds", 20)),
            max_response_size=min(
                int(job.settings_snapshot.get("max_response_size", 5_000_000)),
                1_000_000,
            ),
        )
    except CrawlError:
        return None
    if result.status_code != 200:
        return None
    return RobotsRules(
        result.content.decode("utf-8", errors="replace"),
        robots_url,
    )

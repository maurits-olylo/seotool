"""Reconstruct navigation using one crawl, independently of mutable URL depth."""

from collections import defaultdict, deque
from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crawl import CrawlRun, UrlLink, UrlSnapshot
from app.models.discovery import Url
from app.models.website import Website
from app.services.link_filtering import is_non_navigational_link_target
from app.services.url_filtering import is_excluded_url, is_probable_html_page
from app.services.url_normalization import InvalidUrlError, NormalizationOptions, normalize_url

logger = structlog.get_logger()


@dataclass
class CrawlReachability:
    depths: dict[object, int]
    snapshots: dict[object, UrlSnapshot]
    complete: bool


def crawl_reachability(
    db: Session, *, website_id: object, crawl_run_id: object
) -> CrawlReachability:
    """Nofollow links are navigable; excluded/technical targets are outside this graph.

    A reached source without usable HTML makes negative reachability inconclusive.
    Redirect destinations share their source's navigation depth (zero-cost edge).
    No historical UrlSource records or current status/depth fields are used.
    """
    website = db.get(Website, website_id)
    run = db.get(CrawlRun, crawl_run_id)
    if not website or not run or run.website_id != website_id:
        return CrawlReachability({}, {}, False)
    settings = website.settings
    excluded = settings.excluded_url_patterns if settings else []
    options = NormalizationOptions(
        ignored_query_parameters=frozenset(settings.ignored_query_parameters if settings else [])
    )
    urls = {
        url.id: url
        for url in db.scalars(select(Url).where(Url.website_id == website_id))
        if is_probable_html_page(url.normalized_url)
        and not is_excluded_url(url.normalized_url, excluded)
        and not is_non_navigational_link_target(url.normalized_url)
    }
    by_name = {url.normalized_url: url.id for url in urls.values()}
    snapshots = {
        snapshot.url_id: snapshot
        for snapshot in db.scalars(
            select(UrlSnapshot)
            .where(UrlSnapshot.crawl_run_id == crawl_run_id)
            .order_by(UrlSnapshot.checked_at, UrlSnapshot.id)
        )
        if snapshot.url_id in urls
    }
    try:
        root_id = by_name.get(normalize_url(website.base_url, options=options))
    except InvalidUrlError:
        root_id = None
    if root_id is None or run.crawl_type != "full_site_crawl":
        return CrawlReachability({}, snapshots, False)
    edges: dict[object, set[object]] = defaultdict(set)
    for source, target in db.execute(
        select(UrlLink.source_url_id, UrlLink.target_url_id).where(
            UrlLink.crawl_run_id == crawl_run_id, UrlLink.is_internal.is_(True)
        )
    ):
        if source in urls and target in urls and source != target:
            edges[source].add(target)
    navigation_snapshots = dict(snapshots)
    for source, snapshot in snapshots.items():
        if snapshot.status_code != 200 or not snapshot.final_url:
            continue
        try:
            final_id = by_name.get(normalize_url(snapshot.final_url, options=options))
        except InvalidUrlError:
            continue
        if final_id is not None and final_id != source and final_id not in snapshots:
            # The redirected response already contains the destination's HTML, even
            # when the destination was not requested separately during this crawl.
            navigation_snapshots[final_id] = snapshot
            edges[final_id].update(edges[source])
    depths: dict[object, int] = {root_id: 0}
    pending = deque([root_id])
    complete = True
    while pending:
        source = pending.popleft()
        snapshot = navigation_snapshots.get(source)
        if snapshot is None or snapshot.error_message or snapshot.status_code is None:
            complete = False
            continue
        if snapshot.status_code in {404, 410}:
            continue
        if snapshot.status_code != 200 or snapshot.content_type not in {
            "text/html",
            "application/xhtml+xml",
        }:
            complete = False
            continue
        neighbours = [(target, 1) for target in edges[source]]
        if snapshot.final_url:
            try:
                final_id = by_name.get(normalize_url(snapshot.final_url, options=options))
            except InvalidUrlError:
                final_id = None
            if final_id is not None and final_id != source:
                neighbours.append((final_id, 0))
        for target, cost in neighbours:
            depth = depths[source] + cost
            if target not in depths or depth < depths[target]:
                depths[target] = depth
                pending.append(target)
    # A failed root cannot prove anything about the website's navigation.
    root = snapshots.get(root_id)
    complete = complete and root is not None and root.status_code == 200
    logger.info(
        "crawl_reachability_evaluated",
        website_id=str(website_id),
        crawl_run_id=str(crawl_run_id),
        reachable=len(depths),
        complete=complete,
    )
    return CrawlReachability(depths, snapshots, complete)


def update_crawl_depths(db: Session, *, website_id: object, crawl_run_id: object) -> None:
    """Called only for the current full crawl; historical analysis remains read-only here."""
    graph = crawl_reachability(db, website_id=website_id, crawl_run_id=crawl_run_id)
    for url in db.scalars(select(Url).where(Url.website_id == website_id)):
        url.crawl_depth = graph.depths.get(url.id)

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlLink, UrlSnapshot
from app.models.discovery import CrawlJob, Url, UrlSource
from app.models.issues import Issue
from app.models.website import Website, WebsiteSettings
from app.services.crawl_reachability import crawl_reachability
from app.services.internal_link_analysis import detect_orphan_pages


def _graph(db: Session) -> tuple[Website, CrawlRun, dict[str, Url]]:
    website = Website(client=Client(name="Graph"), name="Graph", base_url="https://example.com/")
    website.settings = WebsiteSettings()
    db.add(website)
    db.flush()
    job = CrawlJob(website_id=website.id, job_type="full_site_crawl")
    db.add(job)
    db.flush()
    run = CrawlRun(website_id=website.id, crawl_job_id=job.id, crawl_type="full_site_crawl")
    db.add(run)
    db.flush()
    urls = {}
    for path in ("/", "/section", "/deep", "/isolated"):
        url = Url(website_id=website.id, normalized_url=f"https://example.com{path}")
        db.add(url)
        db.flush()
        urls[path] = url
        db.add(
            UrlSource(
                url_id=url.id, source_type="sitemap", source_url="https://example.com/sitemap.xml"
            )
        )
        db.add(
            UrlSnapshot(
                url_id=url.id,
                crawl_run_id=run.id,
                requested_url=url.normalized_url,
                final_url=url.normalized_url,
                status_code=200,
                is_indexable=True,
                content_type="text/html",
            )
        )
    db.flush()
    return website, run, urls


def _link(db: Session, run: CrawlRun, source: Url, target: Url) -> None:
    db.add(
        UrlLink(
            crawl_run_id=run.id,
            source_url_id=source.id,
            target_url_id=target.id,
            target_url=target.normalized_url,
            is_internal=True,
            is_nofollow=True,
        )
    )
    db.flush()


def test_orphans_use_run_graph_not_mutable_depth_or_status() -> None:
    with SessionLocal() as db:
        site, run, urls = _graph(db)
        _link(db, run, urls["/"], urls["/section"])
        _link(db, run, urls["/section"], urls["/deep"])
        _link(db, run, urls["/isolated"], urls["/isolated"])
        urls["/isolated"].crawl_depth = 1  # Current register may belong to a later crawl.
        urls["/isolated"].current_status_code = 404
        found = detect_orphan_pages(db, website_id=site.id, crawl_run_id=run.id)
        assert [u.id for u in found] == [urls["/isolated"].id]
        graph = crawl_reachability(db, website_id=site.id, crawl_run_id=run.id)
        assert graph.depths[urls["/deep"].id] == 2
        issue = db.scalar(select(Issue).where(Issue.issue_type == "orphan_page"))
        assert issue and issue.status == "new"
        _link(db, run, urls["/deep"], urls["/isolated"])
        assert detect_orphan_pages(db, website_id=site.id, crawl_run_id=run.id) == []
        assert issue.status == "review"  # Same-run corrected evidence is not a repair.
        assert issue.resolved_at is None


@pytest.mark.parametrize("failure", ["missing", "timeout", "root404"])
def test_incomplete_reachable_sources_do_not_create_or_resolve_orphans(failure: str) -> None:
    with SessionLocal() as db:
        site, run, urls = _graph(db)
        _link(db, run, urls["/"], urls["/section"])
        target = urls["/"] if failure == "root404" else urls["/section"]
        snapshot = db.scalar(select(UrlSnapshot).where(UrlSnapshot.url_id == target.id))
        assert snapshot
        if failure == "missing":
            db.delete(snapshot)
        else:
            snapshot.status_code = 404 if failure == "root404" else None
        issue = Issue(
            website_id=site.id,
            url_id=urls["/isolated"].id,
            issue_type="orphan_page",
            category="internal_links",
            severity="medium",
            title="Old",
            description="Old",
            recommended_action="Old",
        )
        db.add(issue)
        db.flush()
        assert detect_orphan_pages(db, website_id=site.id, crawl_run_id=run.id) == []
        assert issue.status == "new"
        if failure == "root404":
            graph = crawl_reachability(db, website_id=site.id, crawl_run_id=run.id)
            assert graph.depths == {}
            assert graph.blockers == {urls["/"].id: "root_unavailable"}


def test_isolated_linked_group_and_stale_sources_do_not_prove_root_route() -> None:
    with SessionLocal() as db:
        site, run, urls = _graph(db)
        _link(db, run, urls["/section"], urls["/deep"])
        _link(db, run, urls["/deep"], urls["/section"])
        db.add(
            UrlSource(
                url_id=urls["/section"].id,
                source_type="internal_link",
                source_url=urls["/"].normalized_url,
                last_seen_at=run.started_at - timedelta(days=1),
            )
        )
        found = detect_orphan_pages(db, website_id=site.id, crawl_run_id=run.id)
        assert {u.id for u in found} == {urls[p].id for p in ("/section", "/deep", "/isolated")}


def test_old_sitemap_membership_and_unchecked_urls_do_not_create_orphans() -> None:
    with SessionLocal() as db:
        site, run, urls = _graph(db)
        for source in db.scalars(select(UrlSource)):
            source.last_seen_at = run.started_at - timedelta(days=1)
        assert detect_orphan_pages(db, website_id=site.id, crawl_run_id=run.id) == []
        source = db.scalar(select(UrlSource).where(UrlSource.url_id == urls["/isolated"].id))
        assert source
        source.last_seen_at = run.started_at
        snapshot = db.scalar(select(UrlSnapshot).where(UrlSnapshot.url_id == urls["/isolated"].id))
        assert snapshot
        db.delete(snapshot)
        assert detect_orphan_pages(db, website_id=site.id, crawl_run_id=run.id) == []


def test_redirect_destination_has_same_depth_and_other_run_links_are_ignored() -> None:
    with SessionLocal() as db:
        site, run, urls = _graph(db)
        root = db.scalar(select(UrlSnapshot).where(UrlSnapshot.url_id == urls["/"].id))
        assert root
        root.final_url = urls["/section"].normalized_url
        _link(db, run, urls["/section"], urls["/deep"])
        other_job = CrawlJob(website_id=site.id, job_type="full_site_crawl")
        db.add(other_job)
        db.flush()
        other_run = CrawlRun(
            website_id=site.id, crawl_job_id=other_job.id, crawl_type="full_site_crawl"
        )
        db.add(other_run)
        db.flush()
        _link(db, other_run, urls["/"], urls["/isolated"])
        graph = crawl_reachability(db, website_id=site.id, crawl_run_id=run.id)
        assert graph.complete
        assert graph.depths[urls["/section"].id] == 0
        assert graph.depths[urls["/deep"].id] == 1
        assert urls["/isolated"].id not in graph.depths


def test_redirect_response_covers_destination_without_separate_request() -> None:
    with SessionLocal() as db:
        site, run, urls = _graph(db)
        root = db.scalar(select(UrlSnapshot).where(UrlSnapshot.url_id == urls["/"].id))
        destination = db.scalar(
            select(UrlSnapshot).where(UrlSnapshot.url_id == urls["/section"].id)
        )
        assert root and destination
        root.final_url = urls["/section"].normalized_url
        db.delete(destination)
        _link(db, run, urls["/"], urls["/deep"])
        graph = crawl_reachability(db, website_id=site.id, crawl_run_id=run.id)
        assert graph.complete
        assert graph.depths[urls["/section"].id] == 0
        assert graph.depths[urls["/deep"].id] == 1


def test_excluded_and_technical_targets_do_not_block_navigation_evidence() -> None:
    with SessionLocal() as db:
        site, run, urls = _graph(db)
        site.settings.excluded_url_patterns = ["*/isolated"]
        _link(db, run, urls["/"], urls["/isolated"])
        _link(db, run, urls["/"], urls["/section"])
        graph = crawl_reachability(db, website_id=site.id, crawl_run_id=run.id)
        assert graph.complete
        assert urls["/isolated"].id not in graph.depths


def test_partial_graph_reviews_proven_route_but_keeps_unknown_issue() -> None:
    with SessionLocal() as db:
        site, run, urls = _graph(db)
        _link(db, run, urls["/"], urls["/section"])
        _link(db, run, urls["/"], urls["/deep"])
        missing = db.scalar(select(UrlSnapshot).where(UrlSnapshot.url_id == urls["/deep"].id))
        assert missing
        db.delete(missing)
        issues = {}
        for path in ("/section", "/isolated"):
            issue = Issue(
                website_id=site.id,
                url_id=urls[path].id,
                issue_type="orphan_page",
                category="internal_links",
                severity="medium",
                title="Old",
                description="Old",
                recommended_action="Old",
            )
            db.add(issue)
            issues[path] = issue
        db.flush()
        graph = crawl_reachability(db, website_id=site.id, crawl_run_id=run.id)
        assert graph.complete is False
        assert graph.blockers == {urls["/deep"].id: "missing_snapshot"}
        assert detect_orphan_pages(db, website_id=site.id, crawl_run_id=run.id) == []
        assert issues["/section"].status == "review"
        assert issues["/section"].resolved_at is None
        assert issues["/isolated"].status == "new"
        assert issues["/isolated"].recommended_action == "Old"


@pytest.mark.parametrize(
    "status,content_type,error,reason",
    [
        (500, "text/html", None, "http_status_not_usable"),
        (200, "application/pdf", None, "content_type_not_html"),
        (None, None, "timeout", "fetch_error"),
        (None, None, None, "missing_status"),
    ],
)
def test_blocker_reasons_distinguish_measurement_gaps(status, content_type, error, reason) -> None:  # type: ignore[no-untyped-def]
    with SessionLocal() as db:
        site, run, urls = _graph(db)
        _link(db, run, urls["/"], urls["/deep"])
        snapshot = db.scalar(select(UrlSnapshot).where(UrlSnapshot.url_id == urls["/deep"].id))
        assert snapshot
        snapshot.status_code = status
        snapshot.content_type = content_type
        snapshot.error_message = error
        graph = crawl_reachability(db, website_id=site.id, crawl_run_id=run.id)
        assert not graph.complete
        assert graph.blockers == {urls["/deep"].id: reason}


@pytest.mark.parametrize("anchor_present", [False, True])
def test_historical_form_edge_uses_element_evidence_and_preserves_real_anchor(
    anchor_present: bool,
) -> None:
    from app.models.crawl import ElementLocation

    with SessionLocal() as db:
        site, run, urls = _graph(db)
        _link(db, run, urls["/"], urls["/deep"])
        root_snapshot = db.scalar(select(UrlSnapshot).where(UrlSnapshot.url_id == urls["/"].id))
        failed = db.scalar(select(UrlSnapshot).where(UrlSnapshot.url_id == urls["/deep"].id))
        assert root_snapshot and failed
        failed.status_code = 500
        for element_type in ["button", "a"] if anchor_present else ["button"]:
            db.add(
                ElementLocation(
                    website_id=site.id,
                    source_url_id=urls["/"].id,
                    snapshot_id=root_snapshot.id,
                    crawl_run_id=run.id,
                    element_type=element_type,
                    target_url=urls["/deep"].normalized_url,
                    html_fragment="<button>Send</button>",
                )
            )
        db.flush()
        graph = crawl_reachability(db, website_id=site.id, crawl_run_id=run.id)
        assert graph.complete is (not anchor_present)
        assert (urls["/deep"].id in graph.depths) is anchor_present
        assert bool(graph.blockers) is anchor_present


def test_old_form_evidence_does_not_hide_a_link_in_a_new_crawl() -> None:
    from app.models.crawl import ElementLocation

    with SessionLocal() as db:
        site, run, urls = _graph(db)
        _link(db, run, urls["/"], urls["/deep"])
        other_job = CrawlJob(website_id=site.id, job_type="full_site_crawl")
        db.add(other_job)
        db.flush()
        other_run = CrawlRun(
            website_id=site.id, crawl_job_id=other_job.id, crawl_type="full_site_crawl"
        )
        db.add(other_run)
        db.flush()
        snapshot = db.scalar(select(UrlSnapshot).where(UrlSnapshot.url_id == urls["/"].id))
        assert snapshot
        db.add(
            ElementLocation(
                website_id=site.id,
                source_url_id=urls["/"].id,
                snapshot_id=snapshot.id,
                crawl_run_id=other_run.id,
                element_type="button",
                target_url=urls["/deep"].normalized_url,
                html_fragment="<button>Send</button>",
            )
        )
        db.flush()
        graph = crawl_reachability(db, website_id=site.id, crawl_run_id=run.id)
        assert graph.depths[urls["/deep"].id] == 1

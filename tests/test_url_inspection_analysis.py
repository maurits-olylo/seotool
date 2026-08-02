from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url, UrlSource
from app.models.integrations import UrlInspectionResult
from app.models.issues import Change, Issue, IssueOccurrence
from app.models.website import Website, WebsiteSettings
from app.services.url_inspection_analysis import analyze_url_inspection_result


def test_combines_current_google_and_crawler_indexation_evidence() -> None:
    with SessionLocal() as db:
        website, url, snapshot = _context(db)
        db.add(
            UrlSource(
                url_id=url.id,
                source_type="sitemap",
                source_url="https://example.com/sitemap.xml",
            )
        )
        result = _inspection(
            website.id,
            url.id,
            verdict="NEUTRAL",
            robots_txt_state="DISALLOWED",
            page_fetch_state="BLOCKED_ROBOTS_TXT",
            google_canonical="https://example.com/other",
        )
        db.add(result)
        db.flush()

        issues = analyze_url_inspection_result(db, result)

        assert {issue.issue_type for issue in issues} == {
            "google_canonical_mismatch",
            "google_fetch_failed",
            "google_not_indexed",
            "google_robots_blocked",
        }
        occurrence = db.scalar(
            select(IssueOccurrence)
            .join(Issue, Issue.id == IssueOccurrence.issue_id)
            .where(Issue.issue_type == "google_canonical_mismatch")
        )
        assert occurrence is not None
        assert occurrence.snapshot_id == snapshot.id
        assert occurrence.evidence["source"] == "google_url_inspection"


def test_does_not_raise_hard_conflict_when_google_crawl_predates_change() -> None:
    with SessionLocal() as db:
        website, url, snapshot = _context(db, important=True)
        google_crawl = datetime.now(UTC) - timedelta(days=3)
        db.add(
            Change(
                website_id=website.id,
                url_id=url.id,
                previous_snapshot_id=None,
                current_snapshot_id=snapshot.id,
                change_type="canonical_changed",
                field_name="canonical",
                old_value="https://example.com/old",
                new_value=url.normalized_url,
                detected_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        result = _inspection(
            website.id,
            url.id,
            verdict="NEUTRAL",
            google_canonical="https://example.com/old",
            last_crawl_time=google_crawl,
        )
        db.add(result)
        db.flush()

        assert analyze_url_inspection_result(db, result) == []


def test_resolves_conflict_after_new_passing_inspection() -> None:
    with SessionLocal() as db:
        website, url, _ = _context(db, important=True)
        first = _inspection(website.id, url.id, verdict="NEUTRAL")
        db.add(first)
        db.flush()
        analyze_url_inspection_result(db, first)
        issue = db.scalar(select(Issue).where(Issue.issue_type == "google_not_indexed"))
        assert issue is not None
        second = _inspection(website.id, url.id, verdict="PASS")
        db.add(second)
        db.flush()

        analyze_url_inspection_result(db, second)

        db.flush()
        db.refresh(issue)
        assert issue.status == "resolved"


def _context(db, *, important=False):  # type: ignore[no-untyped-def]
    client = Client(name="Inspection analysis client")
    website = Website(client=client, name="Inspection site", base_url="https://example.com/")
    website.settings = WebsiteSettings()
    db.add(website)
    db.flush()
    url = Url(
        website_id=website.id,
        normalized_url="https://example.com/page",
        current_status_code=200,
        is_active=True,
        is_indexable=True,
        is_important=important,
    )
    job = CrawlJob(website_id=website.id, job_type="full_site_crawl")
    db.add_all([url, job])
    db.flush()
    run = CrawlRun(
        crawl_job_id=job.id,
        website_id=website.id,
        crawl_type="full_site_crawl",
    )
    db.add(run)
    db.flush()
    snapshot = UrlSnapshot(
        url_id=url.id,
        crawl_run_id=run.id,
        requested_url=url.normalized_url,
        final_url=url.normalized_url,
        status_code=200,
        redirect_chain=[],
        content_type="text/html",
        canonical=url.normalized_url,
        canonical_urls=[url.normalized_url],
        is_indexable=True,
    )
    db.add(snapshot)
    db.flush()
    return website, url, snapshot


def _inspection(
    website_id,
    url_id,
    *,
    verdict,
    robots_txt_state="ALLOWED",
    page_fetch_state="SUCCESSFUL",
    google_canonical="https://example.com/page",
    last_crawl_time=None,
):  # type: ignore[no-untyped-def]
    return UrlInspectionResult(
        website_id=website_id,
        url_id=url_id,
        inspected_at=datetime.now(UTC),
        verdict=verdict,
        robots_txt_state=robots_txt_state,
        page_fetch_state=page_fetch_state,
        google_canonical=google_canonical,
        last_crawl_time=last_crawl_time or datetime.now(UTC) - timedelta(days=1),
    )

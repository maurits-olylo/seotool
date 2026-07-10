from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.issues import Issue, IssueOccurrence
from app.models.website import Website, WebsiteSettings
from app.services.issue_engine import reconcile_issues, verify_resolved_issues
from app.services.technical_checks import IssueSignal


def test_issue_deduplication_resolution_verification_and_reopen() -> None:
    with SessionLocal() as db:
        client = Client(name="Issue client")
        website = Website(client=client, name="Issue site", base_url="https://example.com")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        url = Url(website_id=website.id, normalized_url="https://example.com/missing")
        db.add(url)
        db.flush()
        signal = IssueSignal("http_404", "reachability", "high", "404", "404", "Fix", {})

        first_run, first_snapshot = _run(db, website.id, url.id)
        reconcile_issues(
            db,
            website_id=website.id,
            url_id=url.id,
            crawl_run_id=first_run.id,
            snapshot_id=first_snapshot.id,
            signals=[signal],
            checked_issue_types={"http_404"},
        )
        second_run, second_snapshot = _run(db, website.id, url.id)
        reconcile_issues(
            db,
            website_id=website.id,
            url_id=url.id,
            crawl_run_id=second_run.id,
            snapshot_id=second_snapshot.id,
            signals=[signal],
            checked_issue_types={"http_404"},
        )
        assert len(list(db.scalars(select(Issue)))) == 1
        assert len(list(db.scalars(select(IssueOccurrence)))) == 2

        third_run, third_snapshot = _run(db, website.id, url.id)
        reconcile_issues(
            db,
            website_id=website.id,
            url_id=url.id,
            crawl_run_id=third_run.id,
            snapshot_id=third_snapshot.id,
            signals=[],
            checked_issue_types={"http_404"},
        )
        issue = db.scalar(select(Issue))
        assert issue and issue.status == "resolved"
        assert verify_resolved_issues(db, website_id=website.id, url_id=url.id) == 1
        assert issue.status == "verified"

        fourth_run, fourth_snapshot = _run(db, website.id, url.id)
        reconcile_issues(
            db,
            website_id=website.id,
            url_id=url.id,
            crawl_run_id=fourth_run.id,
            snapshot_id=fourth_snapshot.id,
            signals=[signal],
            checked_issue_types={"http_404"},
        )
        assert issue.status == "new"


def _run(db, website_id, url_id):  # type: ignore[no-untyped-def]
    job = CrawlJob(website_id=website_id, job_type="light_check")
    db.add(job)
    db.flush()
    run = CrawlRun(crawl_job_id=job.id, website_id=website_id, crawl_type="light_check")
    db.add(run)
    db.flush()
    snapshot = UrlSnapshot(
        url_id=url_id,
        crawl_run_id=run.id,
        requested_url="https://example.com/missing",
        status_code=404,
    )
    db.add(snapshot)
    db.flush()
    return run, snapshot

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.issues import Issue, IssueOccurrence, IssueSuppression
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


def test_second_clean_check_verifies_resolved_issue() -> None:
    with SessionLocal() as db:
        client = Client(name="Verification client")
        website = Website(client=client, name="Verification site", base_url="https://example.com")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        url = Url(website_id=website.id, normalized_url="https://example.com/page")
        db.add(url)
        db.flush()
        issue = Issue(
            website_id=website.id,
            url_id=url.id,
            issue_type="missing_title",
            category="onpage",
            severity="medium",
            title="Title ontbreekt",
            description="Test",
            recommended_action="Herstel",
        )
        db.add(issue)
        db.flush()

        first_run, first_snapshot = _run(db, website.id, url.id)
        reconcile_issues(
            db,
            website_id=website.id,
            url_id=url.id,
            crawl_run_id=first_run.id,
            snapshot_id=first_snapshot.id,
            signals=[],
            checked_issue_types={"missing_title"},
        )
        assert issue.status == "resolved"

        second_run, second_snapshot = _run(db, website.id, url.id)
        reconcile_issues(
            db,
            website_id=website.id,
            url_id=url.id,
            crawl_run_id=second_run.id,
            snapshot_id=second_snapshot.id,
            signals=[],
            checked_issue_types={"missing_title"},
        )
        assert issue.status == "verified"
        assert issue.verified_at is not None


def test_active_suppression_prevents_exact_issue_from_reopening() -> None:
    with SessionLocal() as db:
        client = Client(name="Suppression client")
        website = Website(client=client, name="Suppression site", base_url="https://example.com")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        url = Url(website_id=website.id, normalized_url="https://example.com/page")
        other_url = Url(website_id=website.id, normalized_url="https://example.com/other")
        db.add_all([url, other_url])
        db.flush()
        suppressed_issue = Issue(
            website_id=website.id,
            url_id=url.id,
            issue_type="missing_title",
            category="onpage",
            severity="medium",
            status="ignored",
            title="Title ontbreekt",
            description="Test",
            recommended_action="Herstel",
        )
        db.add_all(
            [
                suppressed_issue,
                IssueSuppression(
                    website_id=website.id,
                    url_id=url.id,
                    issue_type="missing_title",
                    actor="tester@example.com",
                ),
            ]
        )
        db.flush()
        signal = IssueSignal(
            "missing_title", "onpage", "medium", "Title ontbreekt", "Test", "Herstel", {}
        )

        run, snapshot = _run(db, website.id, url.id)
        touched = reconcile_issues(
            db,
            website_id=website.id,
            url_id=url.id,
            crawl_run_id=run.id,
            snapshot_id=snapshot.id,
            signals=[signal],
            checked_issue_types={"missing_title"},
        )
        assert touched == []
        assert suppressed_issue.status == "ignored"
        assert not list(
            db.scalars(
                select(IssueOccurrence).where(IssueOccurrence.issue_id == suppressed_issue.id)
            )
        )

        other_run, other_snapshot = _run(db, website.id, other_url.id)
        touched = reconcile_issues(
            db,
            website_id=website.id,
            url_id=other_url.id,
            crawl_run_id=other_run.id,
            snapshot_id=other_snapshot.id,
            signals=[signal],
            checked_issue_types={"missing_title"},
        )
        assert len(touched) == 1
        assert touched[0].status == "new"


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

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun
from app.models.discovery import CrawlJob, Url
from app.models.issues import Issue, IssueOccurrence
from app.models.website import Website, WebsiteSettings
from app.services.server_error_analysis import analyze_server_error_incident


def test_groups_same_crawl_server_errors_as_one_incident() -> None:
    with SessionLocal() as db:
        website, run = _website_and_run(db)
        for number in range(5):
            _server_error(db, website.id, run.id, f"https://example.com/page-{number}", 502)
        db.flush()

        found = analyze_server_error_incident(
            db, website_id=website.id, crawl_run_id=run.id
        )
        db.flush()

        assert len(found) == 1
        assert found[0].issue_type == "server_error_incident"
        assert found[0].confidence == "medium"
        occurrence = db.scalar(
            select(IssueOccurrence).where(IssueOccurrence.issue_id == found[0].id)
        )
        assert occurrence is not None
        assert occurrence.evidence["affected_url_count"] == 5
        assert occurrence.evidence["patterns"][0]["status_code"] == 502
        assert occurrence.evidence["patterns"][0]["url_count"] == 5


def test_does_not_group_two_errors_and_resolves_previous_incident() -> None:
    with SessionLocal() as db:
        website, first_run = _website_and_run(db)
        for number in range(3):
            _server_error(db, website.id, first_run.id, f"https://example.com/old-{number}", 503)
        grouped = analyze_server_error_incident(
            db, website_id=website.id, crawl_run_id=first_run.id
        )
        db.flush()
        assert len(grouped) == 1

        second_run = _run(db, website.id)
        for number in range(2):
            _server_error(db, website.id, second_run.id, f"https://example.com/new-{number}", 503)
        db.flush()

        assert (
            analyze_server_error_incident(
                db, website_id=website.id, crawl_run_id=second_run.id
            )
            == []
        )
        assert grouped[0].status == "resolved"


def _website_and_run(db):  # type: ignore[no-untyped-def]
    client = Client(name="Incident client")
    website = Website(client=client, name="Incident site", base_url="https://example.com")
    website.settings = WebsiteSettings()
    db.add(website)
    db.flush()
    return website, _run(db, website.id)


def _run(db, website_id):  # type: ignore[no-untyped-def]
    job = CrawlJob(website_id=website_id, job_type="full_site_crawl")
    db.add(job)
    db.flush()
    run = CrawlRun(
        crawl_job_id=job.id,
        website_id=website_id,
        crawl_type="full_site_crawl",
    )
    db.add(run)
    db.flush()
    return run


def _server_error(db, website_id, run_id, url_value, status_code):  # type: ignore[no-untyped-def]
    url = Url(website_id=website_id, normalized_url=url_value)
    db.add(url)
    db.flush()
    issue = Issue(
        website_id=website_id,
        url_id=url.id,
        issue_type="http_5xx",
        category="reachability",
        severity="critical",
        title="Serverfout",
        description="De URL gaf een serverfout.",
        recommended_action="Onderzoek de serverfout.",
    )
    db.add(issue)
    db.flush()
    db.add(
        IssueOccurrence(
            issue_id=issue.id,
            crawl_run_id=run_id,
            evidence={"status_code": status_code},
        )
    )

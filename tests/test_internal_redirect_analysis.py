from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun
from app.models.discovery import CrawlJob, Url
from app.models.issues import Issue, IssueOccurrence
from app.models.website import Website, WebsiteSettings
from app.services.internal_redirect_analysis import analyze_internal_redirect_patterns


def test_groups_legacy_html_redirects_as_one_pattern() -> None:
    with SessionLocal() as db:
        website, run = _website_and_run(db)
        for number in range(4):
            source = f"https://example.com/archive/page-{number}.html"
            final = f"https://example.com/archive/page-{number}"
            _redirect_issue(db, website.id, run.id, source, final)
        db.flush()

        found = analyze_internal_redirect_patterns(
            db, website_id=website.id, crawl_run_id=run.id
        )
        db.flush()

        assert len(found) == 1
        occurrence = db.scalar(
            select(IssueOccurrence).where(IssueOccurrence.issue_id == found[0].id)
        )
        assert occurrence is not None
        pattern = occurrence.evidence["patterns"][0]
        assert pattern["pattern"] == "legacy_html_extension"
        assert pattern["url_count"] == 4


def test_does_not_group_two_unrelated_redirects() -> None:
    with SessionLocal() as db:
        website, run = _website_and_run(db)
        _redirect_issue(
            db,
            website.id,
            run.id,
            "https://example.com/old-one",
            "https://example.com/new-one",
        )
        _redirect_issue(
            db,
            website.id,
            run.id,
            "https://example.com/about-old",
            "https://example.com/about",
        )
        db.flush()

        assert (
            analyze_internal_redirect_patterns(
                db, website_id=website.id, crawl_run_id=run.id
            )
            == []
        )


def _website_and_run(db):  # type: ignore[no-untyped-def]
    client = Client(name="Redirect pattern client")
    website = Website(client=client, name="Redirect site", base_url="https://example.com")
    website.settings = WebsiteSettings()
    db.add(website)
    db.flush()
    job = CrawlJob(website_id=website.id, job_type="full_site_crawl")
    db.add(job)
    db.flush()
    run = CrawlRun(
        crawl_job_id=job.id,
        website_id=website.id,
        crawl_type="full_site_crawl",
    )
    db.add(run)
    db.flush()
    return website, run


def _redirect_issue(db, website_id, run_id, source, final):  # type: ignore[no-untyped-def]
    url = Url(website_id=website_id, normalized_url=source)
    db.add(url)
    db.flush()
    issue = Issue(
        website_id=website_id,
        url_id=url.id,
        issue_type="internally_linked_redirect",
        category="internal_links",
        severity="medium",
        title="Interne links wijzen naar een redirect",
        description="Oud intern doel.",
        recommended_action="Werk de link bij.",
    )
    db.add(issue)
    db.flush()
    db.add(
        IssueOccurrence(
            issue_id=issue.id,
            crawl_run_id=run_id,
            evidence={"redirect_url": source, "final_url": final},
        )
    )

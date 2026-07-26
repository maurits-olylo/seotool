from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun
from app.models.discovery import CrawlJob, Url
from app.models.issues import Issue, IssueOccurrence
from app.models.website import Website, WebsiteSettings
from app.services.sitemap_redirect_analysis import analyze_sitemap_redirect_patterns


def test_groups_repeated_sitemap_redirects_and_preserves_examples() -> None:
    with SessionLocal() as db:
        website, run = _website_and_run(db, "https://example.com")
        for number in range(4):
            source = f"https://example.com/news/item-{number}"
            _redirect_issue(db, website.id, run.id, source, f"{source}/")
        db.flush()

        found = analyze_sitemap_redirect_patterns(
            db, website_id=website.id, crawl_run_id=run.id
        )
        db.flush()

        assert len(found) == 1
        assert found[0].issue_type == "sitemap_redirect_patterns"
        occurrence = db.scalar(
            select(IssueOccurrence).where(IssueOccurrence.issue_id == found[0].id)
        )
        assert occurrence is not None
        assert occurrence.evidence["affected_url_count"] == 4
        pattern = occurrence.evidence["patterns"][0]
        assert pattern["pattern"] == "trailing_slash_added"
        assert pattern["url_count"] == 4
        assert len(pattern["examples"]) == 4
        assert len(pattern["urls"]) == 4


def test_keeps_isolated_redirects_as_individual_actions_and_resolves_old_pattern() -> None:
    with SessionLocal() as db:
        website, first_run = _website_and_run(db, "https://isolated.example")
        for number in range(3):
            source = f"https://isolated.example/old-{number}"
            _redirect_issue(db, website.id, first_run.id, source, f"{source}/")
        grouped = analyze_sitemap_redirect_patterns(
            db, website_id=website.id, crawl_run_id=first_run.id
        )
        db.flush()
        assert len(grouped) == 1

        second_run = _run(db, website.id)
        source = "https://isolated.example/one-off"
        _redirect_issue(db, website.id, second_run.id, source, f"{source}/")
        db.flush()

        assert (
            analyze_sitemap_redirect_patterns(
                db, website_id=website.id, crawl_run_id=second_run.id
            )
            == []
        )
        assert grouped[0].status == "resolved"


def test_does_not_merge_unrelated_other_redirect_families() -> None:
    with SessionLocal() as db:
        website, run = _website_and_run(db, "https://families.example")
        for family in ("news", "events"):
            for number in range(2):
                _redirect_issue(
                    db,
                    website.id,
                    run.id,
                    f"https://families.example/{family}/old-{number}",
                    f"https://families.example/archive/{family}-{number}",
                )
        db.flush()

        assert (
            analyze_sitemap_redirect_patterns(
                db, website_id=website.id, crawl_run_id=run.id
            )
            == []
        )


def _website_and_run(db, base_url):  # type: ignore[no-untyped-def]
    client = Client(name=f"Client {base_url}")
    website = Website(client=client, name="Sitemap site", base_url=base_url)
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


def _redirect_issue(db, website_id, run_id, source, final):  # type: ignore[no-untyped-def]
    url = Url(website_id=website_id, normalized_url=source)
    db.add(url)
    db.flush()
    issue = Issue(
        website_id=website_id,
        url_id=url.id,
        issue_type="sitemap_redirect",
        category="indexation",
        severity="medium",
        title="Sitemap-URL stuurt door",
        description="De sitemap bevat een redirect.",
        recommended_action="Gebruik de eind-URL.",
    )
    db.add(issue)
    db.flush()
    db.add(
        IssueOccurrence(
            issue_id=issue.id,
            crawl_run_id=run_id,
            evidence={"final_url": final},
        )
    )

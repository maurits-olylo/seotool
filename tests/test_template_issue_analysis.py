from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun
from app.models.discovery import CrawlJob, Url
from app.models.issues import Issue, IssueOccurrence
from app.models.website import Website, WebsiteSettings
from app.services.template_issue_analysis import analyze_template_issue_clusters


def test_groups_repeated_template_signals_and_resolves_when_they_disappear() -> None:
    with SessionLocal() as db:
        client = Client(name="Template client")
        website = Website(client=client, name="Template site", base_url="https://example.com")
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

        for number in range(10):
            url = Url(
                website_id=website.id,
                normalized_url=f"https://example.com/articles/item-{number}",
            )
            db.add(url)
            db.flush()
            issue = Issue(
                website_id=website.id,
                url_id=url.id,
                issue_type="deep_page",
                category="internal_links",
                severity="low",
                title="Pagina ligt diep",
                description="Controleer de interne structuur.",
                recommended_action="Controleer de template.",
            )
            db.add(issue)
            db.flush()
            db.add(
                IssueOccurrence(
                    issue_id=issue.id,
                    crawl_run_id=run.id,
                    evidence={"crawl_depth": 5, "related_urls": ["https://example.com/large"] * 50},
                )
            )
        db.flush()

        found = analyze_template_issue_clusters(
            db, website_id=website.id, crawl_run_id=run.id
        )
        db.flush()

        assert len(found) == 1
        occurrence = db.scalar(
            select(IssueOccurrence).where(IssueOccurrence.issue_id == found[0].id)
        )
        assert occurrence is not None
        assert occurrence.evidence["affected_signal_count"] == 10
        assert occurrence.evidence["cluster_count"] == 1
        cluster = occurrence.evidence["clusters"][0]
        assert cluster["cluster_key"] == "/articles/item-{n}/*"
        assert cluster["sample_evidence"] == {"crawl_depth": 5}

        for issue in db.scalars(
            select(Issue).where(Issue.url_id.is_not(None))
        ):
            issue.status = "resolved"
        db.flush()

        assert analyze_template_issue_clusters(
            db, website_id=website.id, crawl_run_id=run.id
        ) == []
        assert found[0].status == "resolved"


def test_does_not_group_duplicate_metadata_without_the_shared_value() -> None:
    with SessionLocal() as db:
        client = Client(name="Missing evidence client")
        website = Website(client=client, name="Missing evidence", base_url="https://example.org")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        job = CrawlJob(website_id=website.id, job_type="full_site_crawl")
        db.add(job)
        db.flush()
        run = CrawlRun(crawl_job_id=job.id, website_id=website.id, crawl_type="full_site_crawl")
        db.add(run)
        db.flush()
        for number in range(3):
            url = Url(website_id=website.id, normalized_url=f"https://example.org/news/{number}")
            db.add(url)
            db.flush()
            db.add(
                Issue(
                    website_id=website.id,
                    url_id=url.id,
                    issue_type="duplicate_title",
                    category="onpage",
                    severity="medium",
                    title="Dubbele title",
                    description="Geen bewijswaarde beschikbaar.",
                    recommended_action="Controleer dit.",
                )
            )
        db.flush()

        assert analyze_template_issue_clusters(
            db, website_id=website.id, crawl_run_id=run.id
        ) == []

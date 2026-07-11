from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlLink
from app.models.discovery import CrawlJob, Url, UrlSource
from app.models.issues import Issue
from app.models.website import Website, WebsiteSettings
from app.services.contextual_404 import classify_404_issues


def test_classifies_linked_and_sitemap_404s_exclusively() -> None:
    with SessionLocal() as db:
        client = Client(name="404 client")
        website = Website(client=client, name="404 site", base_url="https://example.com")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        source = Url(website_id=website.id, normalized_url="https://example.com/")
        linked = Url(
            website_id=website.id,
            normalized_url="https://example.com/linked",
            current_status_code=404,
        )
        sitemap = Url(
            website_id=website.id,
            normalized_url="https://example.com/sitemap-only",
            current_status_code=404,
        )
        db.add_all([source, linked, sitemap])
        db.flush()
        db.add(UrlSource(url_id=sitemap.id, source_type="sitemap", source_url="sitemap.xml"))
        job = CrawlJob(website_id=website.id, job_type="full_site_crawl")
        db.add(job)
        db.flush()
        run = CrawlRun(crawl_job_id=job.id, website_id=website.id, crawl_type="full_site_crawl")
        db.add(run)
        db.flush()
        db.add(
            UrlLink(
                crawl_run_id=run.id,
                source_url_id=source.id,
                target_url=linked.normalized_url,
                target_url_id=linked.id,
                is_internal=True,
                is_nofollow=False,
            )
        )
        db.add(
            Issue(
                website_id=website.id,
                url_id=linked.id,
                issue_type="http_404",
                category="reachability",
                severity="high",
                title="404",
                description="404",
                recommended_action="Fix",
            )
        )
        db.flush()

        classify_404_issues(db, website_id=website.id, crawl_run_id=run.id)

        issues = list(db.scalars(select(Issue).order_by(Issue.issue_type)))
        states = {(issue.url_id, issue.issue_type): issue.status for issue in issues}
        assert states[(linked.id, "http_404")] == "resolved"
        assert states[(linked.id, "internally_linked_404")] == "new"
        assert states[(sitemap.id, "sitemap_404")] == "new"

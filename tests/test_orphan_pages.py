from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun
from app.models.discovery import CrawlJob, Url, UrlSource
from app.models.issues import Issue
from app.models.website import Website, WebsiteSettings
from app.services.internal_link_analysis import detect_orphan_pages
from app.services.issue_engine import reconcile_issues


def test_detects_sitemap_url_without_crawl_depth_as_orphan() -> None:
    with SessionLocal() as db:
        client = Client(name="Orphan client")
        website = Website(client=client, name="Orphan site", base_url="https://example.com/")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        reachable = Url(
            website_id=website.id,
            normalized_url="https://example.com/reachable",
            crawl_depth=1,
        )
        orphan = Url(
            website_id=website.id,
            normalized_url="https://example.com/orphan",
            crawl_depth=None,
        )
        db.add_all([reachable, orphan])
        db.flush()
        db.add_all(
            [
                UrlSource(
                    url_id=reachable.id,
                    source_type="sitemap",
                    source_url="https://example.com/sitemap.xml",
                ),
                UrlSource(
                    url_id=orphan.id,
                    source_type="sitemap",
                    source_url="https://example.com/sitemap.xml",
                ),
            ]
        )
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

        found = detect_orphan_pages(
            db,
            website_id=website.id,
            crawl_run_id=run.id,
        )
        db.flush()
        assert [url.normalized_url for url in found] == ["https://example.com/orphan"]
        issue = db.scalar(select(Issue))
        assert issue and issue.issue_type == "orphan_page"
        assert issue.url_id == orphan.id

        reconcile_issues(
            db,
            website_id=website.id,
            url_id=orphan.id,
            crawl_run_id=run.id,
            snapshot_id=None,
            signals=[],
            checked_issue_types={"http_404", "thin_content"},
        )
        assert issue.status == "new"

        orphan.crawl_depth = 2
        assert (
            detect_orphan_pages(
                db,
                website_id=website.id,
                crawl_run_id=run.id,
            )
            == []
        )
        assert issue.status == "resolved"

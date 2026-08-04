from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun
from app.models.discovery import CrawlJob
from app.models.issues import Issue, IssueOccurrence
from app.models.website import Website, WebsiteSettings
from app.services.robots import RobotsRules
from app.services.sitemap import parse_sitemap
from app.services.sitemap_quality_analysis import (
    SitemapQualityReport,
    reconcile_sitemap_quality,
    record_robots_sitemaps,
    record_sitemap_document,
)


def test_reconciles_grouped_sitemap_and_robots_quality_issues() -> None:
    document = parse_sitemap(
        b"""<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url><loc>/relative</loc></url>
        <url><loc>https://example.com/page</loc><lastmod>wrong</lastmod></url>
        <url><loc>https://example.com/page</loc></url>
        <url></url>
        </urlset>"""
    )
    rules = RobotsRules(
        "Sitemap: /relative.xml\n"
        "Sitemap: https://outside.example/sitemap.xml\n"
        "Sitemap: https://outside.example/sitemap.xml",
        "https://example.com/robots.txt",
    )
    report = SitemapQualityReport()
    record_sitemap_document(
        report,
        document,
        base_url="https://example.com/",
        allowed_subdomains=[],
    )
    record_robots_sitemaps(
        report,
        rules,
        base_url="https://example.com/",
        allowed_subdomains=[],
    )

    with SessionLocal() as db:
        client = Client(name="Quality")
        website = Website(client=client, name="Quality", base_url="https://example.com/")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        job = CrawlJob(
            website_id=website.id,
            job_type="fetch_sitemap",
            settings_snapshot={},
        )
        db.add(job)
        db.flush()
        run = CrawlRun(
            crawl_job_id=job.id,
            website_id=website.id,
            crawl_type="fetch_sitemap",
        )
        db.add(run)
        db.flush()

        reconcile_sitemap_quality(
            db,
            website_id=website.id,
            crawl_run_id=run.id,
            report=report,
        )
        db.commit()

        issues = db.query(Issue).order_by(Issue.issue_type).all()
        assert [issue.issue_type for issue in issues] == [
            "robots_sitemap_configuration",
            "sitemap_document_quality",
        ]
        issue_types = {issue.id: issue.issue_type for issue in issues}
        evidence_by_type = {
            issue_types[occurrence.issue_id]: occurrence.evidence
            for occurrence in db.query(IssueOccurrence).all()
        }
        sitemap_evidence = evidence_by_type["sitemap_document_quality"]
        assert sitemap_evidence["missing_location_count"] == 1
        assert sitemap_evidence["invalid_url_locations"] == ["/relative"]
        assert sitemap_evidence["duplicate_locations"] == ["https://example.com/page"]
        robots_evidence = evidence_by_type["robots_sitemap_configuration"]
        assert robots_evidence["invalid_sitemaps"] == ["/relative.xml"]
        assert robots_evidence["out_of_scope_sitemaps"] == ["https://outside.example/sitemap.xml"]

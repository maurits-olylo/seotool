from types import SimpleNamespace

from app.db.session import SessionLocal
from app.jobs import execute_crawl_job
from app.models.client import Client
from app.models.crawl import CrawlRun
from app.models.discovery import CrawlJob
from app.models.website import Website, WebsiteSettings


def test_sitemap_job_discovers_robots_sitemap_and_counts_unique_urls(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    sitemap = b"""<?xml version="1.0"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/page</loc></url>
      <url><loc>https://example.com/page</loc></url>
      <url><loc>https://example.com/other</loc></url>
    </urlset>"""

    def fetch(url: str, **kwargs):  # type: ignore[no-untyped-def]
        if url.endswith("robots.txt"):
            return SimpleNamespace(
                status_code=200,
                content=b"User-agent: *\nSitemap: https://example.com/site-map.xml",
            )
        assert url == "https://example.com/site-map.xml"
        return SimpleNamespace(status_code=200, content=sitemap)

    monkeypatch.setattr("app.jobs.fetch_url", fetch)
    job_id, website_id = _website_and_job("https://example.com/")

    execute_crawl_job(str(job_id))

    with SessionLocal() as db:
        job = db.get(CrawlJob, job_id)
        run = db.query(CrawlRun).filter(CrawlRun.crawl_job_id == job_id).one()
        website = db.get(Website, website_id)
        assert job is not None and job.status == "succeeded"
        assert run.discovered_urls == 2
        assert run.crawled_urls == 1
        assert website is not None
        assert website.settings.sitemap_urls == ["https://example.com/site-map.xml"]


def test_sitemap_job_fails_clearly_when_no_sitemap_exists(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "app.jobs.fetch_url",
        lambda *args, **kwargs: SimpleNamespace(status_code=404, content=b"not found"),
    )
    job_id, _ = _website_and_job("https://missing.example/")

    execute_crawl_job(str(job_id))

    with SessionLocal() as db:
        job = db.get(CrawlJob, job_id)
        run = db.query(CrawlRun).filter(CrawlRun.crawl_job_id == job_id).one()
        assert job is not None and job.status == "failed"
        assert job.error_message == (
            "Geen sitemap ingesteld of gevonden via robots.txt en /sitemap.xml"
        )
        assert run.status == "failed"
        assert run.discovered_urls == 0
        assert run.crawled_urls == 0


def _website_and_job(base_url: str):  # type: ignore[no-untyped-def]
    with SessionLocal() as db:
        client = Client(name=f"Sitemap {base_url}")
        website = Website(client=client, name="Sitemapsite", base_url=base_url)
        website.settings = WebsiteSettings(sitemap_urls=[])
        db.add(website)
        db.flush()
        job = CrawlJob(
            website_id=website.id,
            job_type="fetch_sitemap",
            settings_snapshot={
                "respect_robots_txt": True,
                "request_timeout_seconds": 20,
                "max_response_size": 5_000_000,
            },
        )
        db.add(job)
        db.commit()
        return job.id, website.id

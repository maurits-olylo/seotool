from sqlalchemy import select

from app.db.session import SessionLocal
from app.jobs import execute_crawl_job
from app.models.client import Client
from app.models.discovery import CrawlJob, Url
from app.models.website import Website, WebsiteSettings
from app.services.http_crawler import FetchResult


def test_full_site_crawl_assigns_breadth_first_depths(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    pages = {
        "https://example.com/": '<main><a href="/section">Section</a></main>',
        "https://example.com/section": '<main><a href="/deep">Deep</a></main>',
        "https://example.com/deep": "<main>Deep page</main>",
    }

    def fake_fetch(url: str, **_: object) -> FetchResult:
        if url.endswith("/robots.txt"):
            return FetchResult(
                requested_url=url,
                final_url=url,
                status_code=200,
                redirect_chain=[],
                headers={"content-type": "text/plain"},
                content=b"User-agent: *\nAllow: /",
                response_time_ms=1,
            )
        return FetchResult(
            requested_url=url,
            final_url=url,
            status_code=200,
            redirect_chain=[],
            headers={"content-type": "text/html; charset=utf-8"},
            content=pages[url].encode(),
            response_time_ms=1,
        )

    monkeypatch.setattr("app.jobs.fetch_url", fake_fetch)
    with SessionLocal() as db:
        client = Client(name="Depth client")
        website = Website(client=client, name="Depth site", base_url="https://example.com/")
        website.settings = WebsiteSettings(sitemap_urls=[], max_urls=10)
        db.add(website)
        db.flush()
        job = CrawlJob(
            website_id=website.id,
            job_type="full_site_crawl",
            settings_snapshot={"max_urls": 10},
        )
        db.add(job)
        db.commit()
        job_id = job.id

    execute_crawl_job(str(job_id))

    with SessionLocal() as db:
        urls = {
            url.normalized_url: url.crawl_depth
            for url in db.scalars(select(Url).order_by(Url.normalized_url))
        }
        assert urls == {
            "https://example.com/": 0,
            "https://example.com/deep": 2,
            "https://example.com/section": 1,
        }
        completed = db.get(CrawlJob, job_id)
        assert completed and completed.status == "succeeded"


def test_limited_full_crawl_is_partial_and_skips_orphan_analysis(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    orphan_analysis_calls: list[object] = []

    def fake_fetch(url: str, **_: object) -> FetchResult:
        content = (
            b"User-agent: *\nAllow: /"
            if url.endswith("robots.txt")
            else b'<main><a href="/next">Next</a></main>'
        )
        return FetchResult(
            requested_url=url,
            final_url=url,
            status_code=200,
            redirect_chain=[],
            headers={"content-type": "text/plain" if url.endswith("robots.txt") else "text/html"},
            content=content,
            response_time_ms=1,
        )

    monkeypatch.setattr("app.jobs.fetch_url", fake_fetch)
    monkeypatch.setattr(
        "app.jobs.detect_orphan_pages",
        lambda *args, **kwargs: orphan_analysis_calls.append(kwargs),
    )
    with SessionLocal() as db:
        client = Client(name="Partial client")
        website = Website(client=client, name="Partial site", base_url="https://example.com/")
        website.settings = WebsiteSettings(sitemap_urls=[], max_urls=1)
        db.add(website)
        db.flush()
        job = CrawlJob(
            website_id=website.id,
            job_type="full_site_crawl",
            settings_snapshot={"max_urls": 1, "respect_robots_txt": True},
        )
        db.add(job)
        db.commit()
        job_id = job.id

    execute_crawl_job(str(job_id))

    with SessionLocal() as db:
        completed = db.get(CrawlJob, job_id)
        assert completed and completed.status == "partially_succeeded"
    assert orphan_analysis_calls == []

from sqlalchemy import select

from app.db.session import SessionLocal
from app.jobs import execute_crawl_job
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.website import Website, WebsiteSettings
from app.services.http_crawler import FetchMetadata, FetchResult


def test_resumed_full_crawl_continues_after_saved_snapshot(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fetched: list[str] = []

    def fake_fetch(url: str, **_: object) -> FetchResult:
        fetched.append(url)
        return FetchResult(
            requested_url=url,
            final_url=url,
            status_code=200,
            redirect_chain=[],
            headers={"content-type": "text/html"},
            content=b"<main>Remaining page</main>",
            response_time_ms=1,
        )

    monkeypatch.setattr("app.jobs.fetch_url", fake_fetch)
    with SessionLocal() as db:
        client = Client(name="Resume client")
        website = Website(client=client, name="Resume site", base_url="https://example.com/")
        website.settings = WebsiteSettings(respect_robots_txt=False)
        db.add(website)
        db.flush()
        root = Url(
            website_id=website.id,
            normalized_url="https://example.com/",
            crawl_depth=0,
        )
        child = Url(
            website_id=website.id,
            normalized_url="https://example.com/remaining",
            crawl_depth=1,
        )
        job = CrawlJob(
            website_id=website.id,
            job_type="full_site_crawl",
            status="pending",
            settings_snapshot={"max_urls": 10, "respect_robots_txt": False},
        )
        db.add_all([root, child, job])
        db.flush()
        run = CrawlRun(
            crawl_job_id=job.id,
            website_id=website.id,
            crawl_type=job.job_type,
            status="paused",
            crawled_urls=1,
        )
        db.add(run)
        db.flush()
        db.add(
            UrlSnapshot(
                url_id=root.id,
                crawl_run_id=run.id,
                requested_url=root.normalized_url,
                final_url=root.normalized_url,
                status_code=200,
                redirect_chain=[],
                is_indexable=True,
            )
        )
        db.commit()
        job_id = job.id

    execute_crawl_job(str(job_id))

    assert fetched == ["https://example.com/remaining"]
    with SessionLocal() as db:
        job = db.get(CrawlJob, job_id)
        run = db.scalar(select(CrawlRun).where(CrawlRun.crawl_job_id == job_id))
        assert job and job.status == "succeeded"
        assert run and run.crawled_urls == 2


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


def test_full_site_crawl_keeps_asset_links_without_fetching_assets(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fetched: list[str] = []
    audited: list[str] = []

    def fake_fetch(url: str, **_: object) -> FetchResult:
        fetched.append(url)
        if url.endswith("robots.txt"):
            content = b"User-agent: *\nAllow: /"
            content_type = "text/plain"
        elif url == "https://example.com/":
            content = (
                b'<main><a href="/page">Page</a><a href="/file.pdf">PDF</a>'
                b'<a href="/photo.JPG?download=1">Photo</a></main>'
            )
            content_type = "text/html"
        else:
            content = b"<main>Page</main>"
            content_type = "text/html"
        return FetchResult(
            requested_url=url,
            final_url=url,
            status_code=200,
            redirect_chain=[],
            headers={"content-type": content_type},
            content=content,
            response_time_ms=1,
        )

    def fake_metadata(url: str, **_: object) -> FetchMetadata:
        audited.append(url)
        return FetchMetadata(
            requested_url=url,
            final_url=url,
            status_code=200,
            redirect_chain=[],
            headers={"content-type": "application/octet-stream", "content-length": "1000"},
            response_time_ms=1,
        )

    monkeypatch.setattr("app.jobs.fetch_url", fake_fetch)
    monkeypatch.setattr("app.jobs.fetch_metadata", fake_metadata)
    with SessionLocal() as db:
        client = Client(name="Asset client")
        website = Website(client=client, name="Asset site", base_url="https://example.com/")
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

    assert "https://example.com/file.pdf" not in fetched
    assert "https://example.com/photo.JPG?download=1" not in fetched
    assert sorted(audited) == [
        "https://example.com/file.pdf",
        "https://example.com/photo.JPG?download=1",
    ]
    with SessionLocal() as db:
        depths = {
            url.normalized_url: url.crawl_depth
            for url in db.scalars(select(Url).order_by(Url.normalized_url))
        }
        assert depths["https://example.com/"] == 0
        assert depths["https://example.com/page"] == 1
        assert depths["https://example.com/file.pdf"] is None
        assert depths["https://example.com/photo.JPG?download=1"] is None
        completed = db.get(CrawlJob, job_id)
        assert completed and completed.status == "succeeded"


def test_light_check_audits_asset_without_page_fetch(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    page_fetches: list[str] = []
    asset_audits: list[str] = []

    monkeypatch.setattr(
        "app.jobs.fetch_url",
        lambda url, **kwargs: page_fetches.append(url),
    )

    def fake_metadata(url: str, **_: object) -> FetchMetadata:
        asset_audits.append(url)
        return FetchMetadata(
            requested_url=url,
            final_url=url,
            status_code=200,
            redirect_chain=[],
            headers={"content-type": "image/jpeg", "content-length": "3000000"},
            response_time_ms=1,
        )

    monkeypatch.setattr("app.jobs.fetch_metadata", fake_metadata)
    with SessionLocal() as db:
        client = Client(name="Light asset client")
        website = Website(client=client, name="Light asset site", base_url="https://example.com/")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        asset = Url(website_id=website.id, normalized_url="https://example.com/photo.jpg")
        db.add(asset)
        db.flush()
        job = CrawlJob(
            website_id=website.id,
            job_type="light_check",
            settings_snapshot={"max_urls": 10, "respect_robots_txt": False},
        )
        db.add(job)
        db.commit()
        job_id = job.id

    execute_crawl_job(str(job_id))

    assert page_fetches == []
    assert asset_audits == ["https://example.com/photo.jpg"]
    with SessionLocal() as db:
        completed = db.get(CrawlJob, job_id)
        assert completed and completed.status == "succeeded"

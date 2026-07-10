from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlLink
from app.models.discovery import CrawlJob, Url
from app.models.website import Website, WebsiteSettings
from app.services.http_crawler import FetchResult
from app.services.snapshot import store_fetch_result


def test_stores_snapshot_and_links() -> None:
    html = (Path(__file__).parent / "fixtures" / "page.html").read_bytes()
    with SessionLocal() as db:
        client = Client(name="Snapshot client")
        website = Website(
            client=client, name="Snapshot site", base_url="https://example.com", status="active"
        )
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        url = Url(website_id=website.id, normalized_url="https://example.com/voorbeeld")
        job = CrawlJob(website_id=website.id, job_type="full_page_analysis")
        db.add_all([url, job])
        db.flush()
        run = CrawlRun(
            crawl_job_id=job.id,
            website_id=website.id,
            crawl_type="full_page_analysis",
        )
        db.add(run)
        db.flush()
        snapshot = store_fetch_result(
            db,
            url=url,
            crawl_run_id=run.id,
            result=FetchResult(
                requested_url=url.normalized_url,
                final_url=url.normalized_url,
                status_code=200,
                redirect_chain=[],
                headers={"content-type": "text/html; charset=utf-8"},
                content=html,
                response_time_ms=12,
            ),
        )
        db.flush()
        assert snapshot.title == "Voorbeeldpagina"
        assert snapshot.is_indexable is True
        assert url.current_status_code == 200
        assert len(list(db.scalars(select(UrlLink)))) == 2

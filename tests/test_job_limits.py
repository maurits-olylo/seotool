from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.jobs import execute_crawl_job
from app.models.client import Client
from app.models.crawl import UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.website import Website, WebsiteSettings
from app.services.http_crawler import FetchResult


def test_light_check_respects_url_limit_and_request_delay(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    delays: list[float] = []

    def fake_fetch(url: str, **_: object) -> FetchResult:
        return FetchResult(
            requested_url=url,
            final_url=url,
            status_code=200,
            redirect_chain=[],
            headers={"content-type": "text/html"},
            content=b"<main>Test page</main>",
            response_time_ms=1,
        )

    monkeypatch.setattr("app.jobs.fetch_url", fake_fetch)
    monkeypatch.setattr("app.jobs.time.sleep", delays.append)
    with SessionLocal() as db:
        client = Client(name="Limited client")
        website = Website(client=client, name="Limited site", base_url="https://example.com/")
        website.settings = WebsiteSettings(max_urls=2, request_delay_ms=750)
        db.add(website)
        db.flush()
        db.add_all(
            [
                Url(website_id=website.id, normalized_url=f"https://example.com/{index}")
                for index in range(3)
            ]
        )
        job = CrawlJob(
            website_id=website.id,
            job_type="light_check",
            settings_snapshot={"max_urls": 2, "request_delay_ms": 750},
        )
        db.add(job)
        db.commit()
        job_id = job.id

    execute_crawl_job(str(job_id))

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(UrlSnapshot)) == 2
        completed = db.get(CrawlJob, job_id)
        assert completed and completed.status == "succeeded"
    assert delays == [0.75, 0.75]

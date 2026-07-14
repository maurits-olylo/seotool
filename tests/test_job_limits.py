from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.jobs import execute_crawl_job
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.issues import Issue
from app.models.website import Website, WebsiteSettings
from app.services.http_crawler import CrawlError, FetchResult


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


def test_every_crawl_deactivates_urls_outside_the_website_scope(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fetched: list[str] = []
    monkeypatch.setattr("app.jobs.fetch_url", lambda url, **_: fetched.append(url))

    with SessionLocal() as db:
        client = Client(name="Pearle")
        website = Website(client=client, name="Pearle NL", base_url="https://www.pearle.nl/")
        website.settings = WebsiteSettings(respect_robots_txt=False)
        db.add(website)
        db.flush()
        polluted = Url(
            website_id=website.id,
            normalized_url="https://jobsatpearle.be/vacatures",
        )
        job = CrawlJob(
            website_id=website.id,
            job_type="light_check",
            settings_snapshot={"respect_robots_txt": False},
        )
        db.add_all([polluted, job])
        db.commit()
        polluted_id = polluted.id
        job_id = job.id

    execute_crawl_job(str(job_id))

    with SessionLocal() as db:
        polluted = db.get(Url, polluted_id)
        completed = db.get(CrawlJob, job_id)
        assert polluted and polluted.is_active is False
        assert completed and completed.status == "succeeded"
    assert fetched == []


def test_job_skips_url_blocked_by_robots_and_creates_issue(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fetched: list[str] = []

    def fake_fetch(url: str, **_: object) -> FetchResult:
        fetched.append(url)
        content = (
            b"User-agent: *\nDisallow: /private"
            if url.endswith("/robots.txt")
            else b"<main>Public page</main>"
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
    with SessionLocal() as db:
        client = Client(name="Robots client")
        website = Website(client=client, name="Robots site", base_url="https://example.com/")
        website.settings = WebsiteSettings(max_urls=2, respect_robots_txt=True)
        db.add(website)
        db.flush()
        db.add_all(
            [
                Url(website_id=website.id, normalized_url="https://example.com/public"),
                Url(website_id=website.id, normalized_url="https://example.com/private"),
            ]
        )
        job = CrawlJob(
            website_id=website.id,
            job_type="light_check",
            settings_snapshot={"max_urls": 2, "respect_robots_txt": True},
        )
        db.add(job)
        db.commit()
        job_id = job.id

    execute_crawl_job(str(job_id))

    assert "https://example.com/private" not in fetched
    with SessionLocal() as db:
        issue = db.scalar(select(Issue))
        run = db.scalar(select(CrawlRun))
        assert issue and issue.issue_type == "robots_txt_blocked"
        assert run and run.crawled_urls == 1 and run.failed_urls == 1


def test_timeout_creates_issue_and_successful_retry_resolves_it(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def timeout_fetch(_: str, **__: object) -> FetchResult:
        raise CrawlError("Timed out", error_type="timeout")

    monkeypatch.setattr("app.jobs.fetch_url", timeout_fetch)
    with SessionLocal() as db:
        client = Client(name="Timeout client")
        website = Website(client=client, name="Timeout site", base_url="https://example.com/")
        website.settings = WebsiteSettings(respect_robots_txt=False)
        db.add(website)
        db.flush()
        db.add(Url(website_id=website.id, normalized_url="https://example.com/slow"))
        failed_job = CrawlJob(
            website_id=website.id,
            job_type="light_check",
            settings_snapshot={"respect_robots_txt": False},
        )
        db.add(failed_job)
        db.commit()
        website_id = website.id
        failed_job_id = failed_job.id

    execute_crawl_job(str(failed_job_id))

    with SessionLocal() as db:
        issue = db.scalar(select(Issue).where(Issue.issue_type == "crawl_timeout"))
        assert issue and issue.status == "new"
        retry_job = CrawlJob(
            website_id=website_id,
            job_type="light_check",
            settings_snapshot={"respect_robots_txt": False},
        )
        db.add(retry_job)
        db.commit()
        retry_job_id = retry_job.id

    def successful_fetch(url: str, **_: object) -> FetchResult:
        return FetchResult(
            requested_url=url,
            final_url=url,
            status_code=200,
            redirect_chain=[],
            headers={"content-type": "text/html"},
            content=b"<main>Page is available again.</main>",
            response_time_ms=1,
        )

    monkeypatch.setattr("app.jobs.fetch_url", successful_fetch)
    execute_crawl_job(str(retry_job_id))

    with SessionLocal() as db:
        issue = db.scalar(select(Issue).where(Issue.issue_type == "crawl_timeout"))
        assert issue and issue.status == "resolved"

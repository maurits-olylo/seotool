from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.discovery import CrawlJob
from app.models.website import Website, WebsiteSettings
from app.scheduler import schedule_due_jobs


def test_scheduler_creates_only_one_due_job_per_website(monkeypatch) -> None:
    queued: list[str] = []
    monkeypatch.setattr(
        "app.scheduler.enqueue_crawl_job",
        lambda job_id, **_kwargs: queued.append(job_id),
    )
    with SessionLocal() as db:
        website = Website(
            client=Client(name="Scheduled client"),
            name="Scheduled website",
            base_url="https://scheduled.test/",
        )
        website.settings = WebsiteSettings()
        db.add(website)
        db.commit()
        website_id = website.id

    assert schedule_due_jobs() == 1

    with SessionLocal() as db:
        jobs = list(db.scalars(select(CrawlJob).where(CrawlJob.website_id == website_id)))
    assert len(jobs) == 1
    assert jobs[0].job_type == "full_site_crawl"
    assert queued == [str(jobs[0].id)]


def test_scheduler_does_not_queue_behind_active_job(monkeypatch) -> None:
    queued: list[str] = []
    monkeypatch.setattr(
        "app.scheduler.enqueue_crawl_job",
        lambda job_id, **_kwargs: queued.append(job_id),
    )
    with SessionLocal() as db:
        website = Website(
            client=Client(name="Busy client"),
            name="Busy website",
            base_url="https://busy.test/",
        )
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        db.add(
            CrawlJob(
                website_id=website.id,
                job_type="light_check",
                status="paused",
            )
        )
        db.commit()

    assert schedule_due_jobs() == 0
    assert queued == []


def test_recent_full_crawl_satisfies_daily_light_and_sitemap_schedule(monkeypatch) -> None:
    queued: list[str] = []
    monkeypatch.setattr(
        "app.scheduler.enqueue_crawl_job",
        lambda job_id, **_kwargs: queued.append(job_id),
    )
    with SessionLocal() as db:
        website = Website(
            client=Client(name="Fresh client"),
            name="Fresh website",
            base_url="https://fresh.test/",
        )
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        db.add(
            CrawlJob(
                website_id=website.id,
                job_type="full_site_crawl",
                status="succeeded",
                created_at=datetime.now(UTC) - timedelta(hours=2),
            )
        )
        db.commit()

    assert schedule_due_jobs() == 0
    assert queued == []

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun
from app.models.discovery import CrawlJob
from app.models.website import Website, WebsiteSettings
from app.worker import recover_interrupted_crawls


def test_worker_restart_pauses_interrupted_crawl() -> None:
    with SessionLocal() as db:
        client = Client(name="Interrupted client")
        website = Website(client=client, name="Interrupted site", base_url="https://example.com/")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        job = CrawlJob(website_id=website.id, job_type="full_site_crawl", status="running")
        db.add(job)
        db.flush()
        db.add(
            CrawlRun(
                crawl_job_id=job.id,
                website_id=website.id,
                crawl_type=job.job_type,
                status="running",
            )
        )
        db.commit()
        job_id = job.id

    recover_interrupted_crawls()

    with SessionLocal() as db:
        job = db.get(CrawlJob, job_id)
        run = db.scalar(select(CrawlRun).where(CrawlRun.crawl_job_id == job_id))
        assert job and job.status == "paused"
        assert job.error_message == "Worker opnieuw gestart; crawl kan veilig worden hervat."
        assert run and run.status == "paused"


def test_worker_restart_finishes_requested_cancellation() -> None:
    with SessionLocal() as db:
        client = Client(name="Cancelled client")
        website = Website(client=client, name="Cancelled site", base_url="https://example.com/")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        job = CrawlJob(
            website_id=website.id,
            job_type="full_site_crawl",
            status="cancel_requested",
        )
        db.add(job)
        db.flush()
        db.add(
            CrawlRun(
                crawl_job_id=job.id,
                website_id=website.id,
                crawl_type=job.job_type,
                status="running",
            )
        )
        db.commit()
        job_id = job.id

    recover_interrupted_crawls()

    with SessionLocal() as db:
        job = db.get(CrawlJob, job_id)
        run = db.scalar(select(CrawlRun).where(CrawlRun.crawl_job_id == job_id))
        assert job and job.status == "cancelled" and job.finished_at is not None
        assert run and run.status == "cancelled" and run.finished_at is not None

from unittest.mock import Mock

from sqlalchemy import select

from app.db.session import SessionLocal
from app.jobs import execute_crawl_job
from app.models.client import Client
from app.models.crawl import CrawlRun
from app.models.discovery import CrawlJob
from app.models.website import Website, WebsiteSettings
from app.worker import recover_interrupted_crawls, worker_is_registered, worker_name


def test_worker_name_is_unique_per_container() -> None:
    assert worker_name("full-1", "container-a") == "full-1-container-a"
    assert worker_name("full-1", "container-b") == "full-1-container-b"


def test_worker_name_keeps_rq_default_without_configured_role() -> None:
    assert worker_name("", "container-a") is None


def test_worker_health_requires_active_registration() -> None:
    redis = Mock()
    redis.exists.return_value = True
    redis.hexists.return_value = False

    assert worker_is_registered(redis, name="full-1-container-a")
    redis.exists.assert_called_once_with("rq:worker:full-1-container-a")
    redis.hexists.assert_called_once_with("rq:worker:full-1-container-a", "death")


def test_worker_health_rejects_missing_or_ended_registration() -> None:
    missing = Mock()
    missing.exists.return_value = False
    ended = Mock()
    ended.exists.return_value = True
    ended.hexists.return_value = True

    assert not worker_is_registered(missing, name="full-1-missing")
    assert not worker_is_registered(ended, name="full-1-ended")


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

    recover_interrupted_crawls(active_job_ids=set())

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

    recover_interrupted_crawls(active_job_ids=set())

    with SessionLocal() as db:
        job = db.get(CrawlJob, job_id)
        run = db.scalar(select(CrawlRun).where(CrawlRun.crawl_job_id == job_id))
        assert job and job.status == "cancelled" and job.finished_at is not None
        assert run and run.status == "cancelled" and run.finished_at is not None


def test_worker_restart_preserves_crawl_owned_by_other_worker() -> None:
    with SessionLocal() as db:
        client = Client(name="Parallel worker client")
        website = Website(client=client, name="Parallel site", base_url="https://parallel.example/")
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

    recover_interrupted_crawls(active_job_ids={str(job_id)})

    with SessionLocal() as db:
        job = db.get(CrawlJob, job_id)
        run = db.scalar(select(CrawlRun).where(CrawlRun.crawl_job_id == job_id))
        assert job and job.status == "running"
        assert run and run.status == "running"


def test_cancellation_interrupts_post_crawl_404_analysis(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    with SessionLocal() as db:
        client = Client(name="Post-analysis cancellation")
        website = Website(client=client, name="Large site", base_url="https://example.com/")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        job = CrawlJob(
            website_id=website.id,
            job_type="light_check",
            settings_snapshot={"max_urls": 100, "request_delay_ms": 0},
        )
        db.add(job)
        db.commit()
        job_id = job.id

    monkeypatch.setattr("app.jobs._load_robots_rules", lambda db, job: None)

    def request_cancel_during_analysis(
        db,
        *,
        website_id,
        crawl_run_id,
        check_control,  # type: ignore[no-untyped-def]
    ) -> None:
        job = db.get(CrawlJob, job_id)
        assert job is not None
        job.status = "cancel_requested"
        db.flush()
        check_control()

    monkeypatch.setattr("app.jobs.classify_404_issues", request_cancel_during_analysis)

    execute_crawl_job(str(job_id))

    with SessionLocal() as db:
        job = db.get(CrawlJob, job_id)
        run = db.scalar(select(CrawlRun).where(CrawlRun.crawl_job_id == job_id))
        assert job and job.status == "cancelled" and job.finished_at is not None
        assert run and run.status == "cancelled" and run.finished_at is not None

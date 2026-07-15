from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.discovery import CrawlJob
from app.models.website import Website
from app.services.crawl_deployment import (
    deployment_drain_status,
    finish_deployment_drain,
    pause_job_if_deployment_active,
    start_deployment_drain,
)


def test_deployment_drain_only_resumes_jobs_it_paused(client) -> None:  # type: ignore[no-untyped-def]
    customer = client.post("/api/v1/clients", json={"name": "Deployment drain"}).json()
    first = client.post(
        "/api/v1/websites",
        json={"client_id": customer["id"], "name": "First", "base_url": "https://first.example"},
    ).json()
    second = client.post(
        "/api/v1/websites",
        json={"client_id": customer["id"], "name": "Second", "base_url": "https://second.example"},
    ).json()
    with SessionLocal() as db:
        running = CrawlJob(
            website_id=UUID(first["id"]), job_type="full_site_crawl", status="running"
        )
        manually_paused = CrawlJob(
            website_id=UUID(second["id"]), job_type="full_site_crawl", status="paused"
        )
        manual_pause_requested = CrawlJob(
            website_id=UUID(second["id"]), job_type="light_check", status="pause_requested"
        )
        db.add_all([running, manually_paused, manual_pause_requested])
        db.commit()
        running_id = running.id
        manual_id = manually_paused.id
        manual_request_id = manual_pause_requested.id

        status = start_deployment_drain(db)
        assert status.active and not status.safe
        assert status.tracked_job_ids == (str(running_id),)
        assert db.get(CrawlJob, running_id).status == "pause_requested"
        assert db.get(CrawlJob, manual_id).status == "paused"
        assert str(manual_request_id) in status.waiting_job_ids

        db.get(CrawlJob, running_id).status = "paused"
        db.get(CrawlJob, manual_request_id).status = "paused"
        db.commit()
        assert deployment_drain_status(db).safe
        resumed = finish_deployment_drain(db)
        assert resumed == [(str(running_id), 1)]
        assert db.get(CrawlJob, running_id).status == "pending"
        assert db.get(CrawlJob, manual_id).status == "paused"
        assert db.get(CrawlJob, manual_request_id).status == "paused"


def test_deployment_drain_blocks_api_and_scheduler_creation(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    customer = client.post("/api/v1/clients", json={"name": "Blocked crawl"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Blocked",
            "base_url": "https://blocked.example",
        },
    ).json()
    paused = client.post("/api/v1/system/crawl-deployment/pause")
    assert paused.status_code == 200
    assert paused.json() == {"active": True, "safe": True, "tracked_jobs": 0, "waiting_jobs": 0}

    rejected = client.post(
        "/api/v1/crawl-jobs",
        json={"website_id": website["id"], "job_type": "full_site_crawl"},
    )
    assert rejected.status_code == 503

    from app.scheduler import schedule_due_jobs

    assert schedule_due_jobs() == 0
    with SessionLocal() as db:
        assert list(db.scalars(select(CrawlJob))) == []
        assert db.get(Website, UUID(website["id"])) is not None

    resumed = client.post("/api/v1/system/crawl-deployment/resume")
    assert resumed.status_code == 200
    assert resumed.json() == {"active": False, "resumed_jobs": 0}


def test_worker_gate_tracks_job_that_was_queued_during_drain_race(client) -> None:  # type: ignore[no-untyped-def]
    customer = client.post("/api/v1/clients", json={"name": "Drain race"}).json()
    website = client.post(
        "/api/v1/websites",
        json={"client_id": customer["id"], "name": "Race", "base_url": "https://race.example"},
    ).json()
    with SessionLocal() as db:
        start_deployment_drain(db)
        job = CrawlJob(website_id=UUID(website["id"]), job_type="full_site_crawl")
        db.add(job)
        db.commit()
        job_id = job.id

        assert pause_job_if_deployment_active(db, job)
        assert job.status == "paused"
        assert deployment_drain_status(db).tracked_job_ids == (str(job_id),)

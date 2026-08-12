from datetime import UTC, datetime
from unittest.mock import Mock

from sqlalchemy import select

from app.api.routes.system import system_status
from app.core.security import Principal
from app.db.session import SessionLocal
from app.models.client import Client
from app.models.discovery import CrawlJob
from app.models.system import QueueDeadLetter, SecurityIncident
from app.models.user import SecurityAuditEvent
from app.models.website import Website, WebsiteSettings
from app.services.security_audit import record_security_event
from app.services.system_status import build_queue_status


class FakeWorker:
    def __init__(self, *queue_names: str) -> None:
        self.queue_names = list(queue_names)


class FakeMethodWorker:
    def __init__(self, *queue_names: str) -> None:
        self._queue_names = list(queue_names)

    def queue_names(self) -> list[str]:
        return self._queue_names


def test_build_queue_status_reports_workers_and_backlog(monkeypatch) -> None:
    redis = Mock()
    monkeypatch.setattr(
        "app.services.system_status.Worker.all",
        lambda connection: [
            FakeWorker("sitemaps", "crawls_light", "verifications"),
            FakeWorker("crawls_full"),
            FakeWorker("integrations", "maintenance"),
            FakeWorker("exports"),
        ],
    )

    class FakeQueue:
        def __init__(self, name: str, connection: object) -> None:
            self.count = {
                "crawls_light": 2,
                "crawls_full": 1,
                "sitemaps": 0,
                "verifications": 0,
                "integrations": 3,
                "maintenance": 0,
                "exports": 1,
            }[name]

    monkeypatch.setattr("app.services.system_status.Queue", FakeQueue)
    result = build_queue_status(redis)

    redis.ping.assert_called_once()
    assert result["queues"]["crawls"] == {
        "status": "ok",
        "workers": 2,
        "queued_jobs": 3,
    }
    assert result["queues"]["crawls_light"] == {
        "status": "ok",
        "workers": 1,
        "queued_jobs": 2,
        "warning_backlog": 25,
        "admission_backlog": 100,
    }
    assert result["queues"]["crawls_full"] == {
        "status": "ok",
        "workers": 1,
        "queued_jobs": 1,
        "warning_backlog": 10,
        "admission_backlog": 25,
    }
    assert result["queues"]["integrations"] == {
        "status": "ok",
        "workers": 1,
        "queued_jobs": 3,
        "warning_backlog": 10,
        "admission_backlog": 50,
    }
    assert result["queues"]["exports"] == {
        "status": "ok",
        "workers": 1,
        "queued_jobs": 1,
        "warning_backlog": 10,
        "admission_backlog": 50,
    }


def test_queue_status_reports_warning_and_blocked_backlog(monkeypatch) -> None:
    redis = Mock()
    monkeypatch.setattr(
        "app.services.system_status.Worker.all",
        lambda connection: [
            FakeWorker("sitemaps", "crawls_light", "verifications"),
            FakeWorker("crawls_full"),
            FakeWorker("integrations", "maintenance"),
            FakeWorker("exports"),
        ],
    )

    class BusyQueue:
        def __init__(self, name: str, connection: object) -> None:
            self.count = {"crawls_light": 25, "crawls_full": 25}.get(name, 0)

    monkeypatch.setattr("app.services.system_status.Queue", BusyQueue)
    result = build_queue_status(redis)

    assert result["queues"]["crawls_light"]["status"] == "warning"
    assert result["queues"]["crawls_full"]["status"] == "blocked"
    assert result["queues"]["crawls"]["status"] == "degraded"


def test_system_status_endpoint_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.routes.system.build_queue_status",
        lambda: {
            "redis": "ok",
            "queues": {
                "crawls": {"status": "ok", "workers": 2, "queued_jobs": 0},
                "integrations": {"status": "ok", "workers": 1, "queued_jobs": 0},
                "exports": {"status": "ok", "workers": 1, "queued_jobs": 0},
            },
        },
    )
    with SessionLocal() as db:
        result = system_status(
            db=db,
            principal=Principal(user_id=None, role="superuser", is_api_key=True),
        )
    assert result["status"] == "ok"
    assert result["database"] == "ok"


def test_build_queue_status_supports_rq_queue_names_method(monkeypatch) -> None:
    redis = Mock()
    monkeypatch.setattr(
        "app.services.system_status.Worker.all",
        lambda connection: [
            FakeMethodWorker("crawls_light", "crawls_full"),
            FakeMethodWorker("integrations"),
            FakeMethodWorker("exports"),
        ],
    )

    class EmptyQueue:
        count = 0

        def __init__(self, name: str, connection: object) -> None:
            pass

    monkeypatch.setattr("app.services.system_status.Queue", EmptyQueue)
    result = build_queue_status(redis)
    assert result["queues"]["crawls"]["workers"] == 1
    assert result["queues"]["integrations"]["workers"] == 1
    assert result["queues"]["exports"]["workers"] == 1


def test_dead_letter_api_lists_and_resolves_failures(client) -> None:  # type: ignore[no-untyped-def]
    with SessionLocal() as db:
        record = QueueDeadLetter(
            queue_name="crawls_full",
            original_job_id="failed-crawl",
            job_type="full_site_crawl",
            failed_at=datetime.now(UTC),
            error_message="terminal failure",
        )
        db.add(record)
        db.commit()
        record_id = record.id

    listed = client.get("/api/v1/system/dead-letters")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [str(record_id)]

    resolved = client.post(
        f"/api/v1/system/dead-letters/{record_id}/resolve",
        json={"resolution": "Handmatig beoordeeld; bronconfiguratie is aangepast."},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    assert client.get("/api/v1/system/dead-letters").json() == []


def test_dead_letter_api_requeues_linked_crawl(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("app.services.dead_letters.enqueue_crawl_job", lambda *args, **kwargs: True)
    with SessionLocal() as db:
        website = Website(
            client=Client(name="Dead letter client"),
            name="Dead letter website",
            base_url="https://dead-letter.test/",
        )
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        job = CrawlJob(
            website_id=website.id,
            job_type="full_site_crawl",
            status="failed",
            error_message="terminal failure",
        )
        db.add(job)
        db.flush()
        record = QueueDeadLetter(
            website_id=website.id,
            queue_name="crawls_full",
            original_job_id=str(job.id),
            job_type="full_site_crawl",
            failed_at=datetime.now(UTC),
            error_message="terminal failure",
            payload={"crawl_job_id": str(job.id), "job_type": "full_site_crawl"},
        )
        db.add(record)
        db.commit()
        record_id = record.id
        job_id = job.id

    response = client.post(f"/api/v1/system/dead-letters/{record_id}/requeue")
    assert response.status_code == 200
    assert response.json()["status"] == "requeued"

    with SessionLocal() as db:
        assert db.get(CrawlJob, job_id).status == "pending"


def test_system_status_reports_unresolved_dead_letters(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.routes.system.build_queue_status",
        lambda: {
            "redis": "ok",
            "queues": {"crawls": {"status": "ok", "workers": 2, "queued_jobs": 0}},
        },
    )
    with SessionLocal() as db:
        db.add(
            QueueDeadLetter(
                queue_name="crawls_full",
                original_job_id="unresolved-job",
                job_type="full_site_crawl",
                failed_at=datetime.now(UTC),
                error_message="terminal failure",
            )
        )
        db.commit()
        result = system_status(
            db=db,
            principal=Principal(user_id=None, role="superuser", is_api_key=True),
        )

    assert result["status"] == "degraded"
    assert result["dead_letters"] == {
        "unresolved": 1,
        "by_queue": {"crawls_full": 1},
    }


def test_security_incident_detection_is_idempotent_and_resolvable(client) -> None:  # type: ignore[no-untyped-def]
    now = datetime.now(UTC)
    with SessionLocal() as db:
        for _offset in range(5):
            db.add(
                SecurityAuditEvent(
                    event_type="authentication.login",
                    result="failed",
                    source_hash="a" * 64,
                    summary="Mislukte inlogpoging",
                    occurred_at=now,
                )
            )
        db.commit()

    first = client.post("/api/v1/system/security-incidents/detect")
    assert first.status_code == 200
    assert len(first.json()) == 1
    listed = client.get("/api/v1/system/security-incidents")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    incident_id = listed.json()[0]["id"]
    assert listed.json()[0]["rule_id"] == "repeated_login_failures"
    assert listed.json()[0]["occurrence_count"] == 5
    status = client.get("/api/v1/system/status").json()
    assert status["status"] == "degraded"
    assert status["security_incidents"] == {"open": 1}

    client.post("/api/v1/system/security-incidents/detect")
    with SessionLocal() as db:
        assert db.query(SecurityIncident).count() == 1

    resolved = client.post(
        f"/api/v1/system/security-incidents/{incident_id}/resolve",
        json={"resolution": "Bron beoordeeld; geen accountovername vastgesteld."},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert client.get("/api/v1/system/security-incidents").json() == []
    assert (
        client.post(
            f"/api/v1/system/security-incidents/{incident_id}/resolve",
            json={"resolution": "kort"},
        ).status_code
        == 422
    )


def test_security_audit_automatically_creates_incident() -> None:
    with SessionLocal() as db:
        for _attempt in range(5):
            record_security_event(
                db,
                event_type="authentication.login",
                result="failed",
                source_hash="b" * 64,
                summary="Mislukte inlogpoging",
            )
        db.commit()
        incident = db.scalar(
            select(SecurityIncident).where(SecurityIncident.source_hash == "b" * 64)
        )

    assert incident is not None
    assert incident.rule_id == "repeated_login_failures"
    assert incident.occurrence_count == 5

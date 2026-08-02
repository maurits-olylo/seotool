from unittest.mock import Mock

from app.api.routes.system import system_status
from app.core.security import Principal
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
    result = system_status(
        db=Mock(),
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

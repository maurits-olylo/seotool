from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.session import engine
from app.models.client import Client
from app.models.discovery import CrawlJob
from app.models.system import QueueDeadLetter
from app.models.website import Website, WebsiteSettings
from app.services.queue_failures import record_dead_letter
from app.services.queue_policy import QUEUE_POLICIES, queue_policy, serialized_queue_policy

SessionLocal = sessionmaker(bind=engine)


def test_queue_policy_is_versioned_and_bounded() -> None:
    policy = serialized_queue_policy()

    assert policy["version"] == "2026-08-04-v3"
    assert policy["priority"]["lower_number_runs_first"] is True
    assert queue_policy("crawls_full").admission_backlog == 25
    assert queue_policy("renders").enabled is True
    assert queue_policy("renders").job_timeout_seconds == 300
    assert queue_policy("performance").admission_backlog == 10
    assert all(item.warning_backlog <= item.admission_backlog for item in QUEUE_POLICIES.values())


def test_unknown_queue_has_no_implicit_policy() -> None:
    with pytest.raises(ValueError, match="Unknown queue"):
        queue_policy("unbounded")


def test_render_enqueue_requires_explicit_feature_gate(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.core import queue

    monkeypatch.setattr(
        queue, "get_settings", lambda: SimpleNamespace(rendering_enabled=False)
    )
    monkeypatch.setattr(
        queue,
        "_enqueue",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must stay disabled")),
    )

    assert queue.enqueue_render_observation("observation", website_id="website") is False


def test_performance_enqueue_requires_explicit_feature_gate(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.core import queue

    monkeypatch.setattr(
        queue, "get_settings", lambda: SimpleNamespace(pagespeed_enabled=False)
    )
    monkeypatch.setattr(
        queue,
        "_enqueue",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must stay disabled")),
    )

    assert (
        queue.enqueue_performance_sync(
            "website", strategy="mobile", limit=10, job_id="performance-job"
        )
        is False
    )


def test_website_queue_settings_enforce_bounds() -> None:
    with SessionLocal() as db:
        website = Website(
            client=Client(name="Queue policy client"),
            name="Queue policy website",
            base_url="https://queue-policy.test/",
        )
        website.settings = WebsiteSettings(queue_priority=101, crawl_queue_limit=1)
        db.add(website)
        with pytest.raises(IntegrityError):
            db.commit()


def test_dead_letter_is_unique_per_queue_job() -> None:
    with SessionLocal() as db:
        failed_at = datetime.now(UTC)
        db.add_all(
            [
                QueueDeadLetter(
                    queue_name="crawls_full",
                    original_job_id="job-1",
                    job_type="full_site_crawl",
                    failed_at=failed_at,
                    error_message="first failure",
                ),
                QueueDeadLetter(
                    queue_name="crawls_full",
                    original_job_id="job-1",
                    job_type="full_site_crawl",
                    failed_at=failed_at,
                    error_message="duplicate failure",
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_crawl_job_priority_enforces_bounds() -> None:
    with SessionLocal() as db:
        website = Website(
            client=Client(name="Crawl priority client"),
            name="Crawl priority website",
            base_url="https://crawl-priority.test/",
        )
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        db.add(
            CrawlJob(
                website_id=website.id,
                job_type="full_site_crawl",
                queue_priority=-1,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_terminal_queue_failure_is_persisted_once() -> None:
    class FailedJob:
        id = "failed-job"
        origin = "crawls_full"
        func_name = "app.jobs.execute_crawl_job"
        should_retry = False
        meta = {"job_type": "full_site_crawl", "max_attempts": 4}

    record_dead_letter(FailedJob(), None, RuntimeError, RuntimeError("crawl failed"), None)
    record_dead_letter(FailedJob(), None, RuntimeError, RuntimeError("crawl failed"), None)

    with SessionLocal() as db:
        records = db.query(QueueDeadLetter).all()
    assert len(records) == 1
    assert records[0].attempt_count == 4
    assert records[0].error_message == "crawl failed"


def test_retryable_queue_failure_is_not_dead_lettered() -> None:
    class RetryableJob:
        id = "retry-job"
        origin = "crawls_full"
        func_name = "app.jobs.execute_crawl_job"
        should_retry = True
        meta = {"job_type": "full_site_crawl", "max_attempts": 4}

    record_dead_letter(RetryableJob(), None, RuntimeError, RuntimeError("temporary"), None)

    with SessionLocal() as db:
        assert db.query(QueueDeadLetter).count() == 0


def test_configured_website_crawl_queue_limit_is_enforced(client) -> None:  # type: ignore[no-untyped-def]
    customer = client.post("/api/v1/clients", json={"name": "Queue limit client"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Queue limit website",
            "base_url": "https://queue-limit.test/",
        },
    ).json()
    settings = client.get(f"/api/v1/websites/{website['id']}/settings").json()
    settings["crawl_queue_limit"] = 2
    updated = client.put(f"/api/v1/websites/{website['id']}/settings", json=settings)
    assert updated.status_code == 200

    first = client.post(
        "/api/v1/crawl-jobs",
        json={"website_id": website["id"], "job_type": "fetch_sitemap"},
    )
    second = client.post(
        "/api/v1/crawl-jobs",
        json={"website_id": website["id"], "job_type": "light_check"},
    )
    blocked = client.post(
        "/api/v1/crawl-jobs",
        json={"website_id": website["id"], "job_type": "full_site_crawl"},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "De crawlwachtrijlimiet is bereikt"

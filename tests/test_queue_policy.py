from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.session import engine
from app.models.client import Client
from app.models.discovery import CrawlJob
from app.models.system import QueueDeadLetter
from app.models.website import Website, WebsiteSettings
from app.services.queue_policy import QUEUE_POLICIES, queue_policy, serialized_queue_policy

SessionLocal = sessionmaker(bind=engine)


def test_queue_policy_is_versioned_and_bounded() -> None:
    policy = serialized_queue_policy()

    assert policy["version"] == "2026-08-02-v1"
    assert policy["priority"]["lower_number_runs_first"] is True
    assert queue_policy("crawls_full").admission_backlog == 25
    assert queue_policy("renders").enabled is False
    assert all(item.warning_backlog <= item.admission_backlog for item in QUEUE_POLICIES.values())


def test_unknown_queue_has_no_implicit_policy() -> None:
    with pytest.raises(ValueError, match="Unknown queue"):
        queue_policy("unbounded")


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

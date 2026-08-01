from datetime import UTC, datetime

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, ElementLocation, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.system import RetentionOperation
from app.models.website import Website
from app.services.retention_operations import (
    create_retention_operation,
    execute_retention_operation,
)


def test_retention_operation_is_idempotent_and_resumable() -> None:
    with SessionLocal() as db:
        website, url = _website_and_url(db)
        old_run, old_snapshot = _run_and_snapshot(db, website, url, 2024)
        latest_run, latest_snapshot = _run_and_snapshot(db, website, url, 2025)
        db.add_all(
            [
                _location(website, url, old_run, old_snapshot),
                _location(website, url, old_run, old_snapshot),
                _location(website, url, latest_run, latest_snapshot),
            ]
        )
        db.commit()
        first = create_retention_operation(db, latest_run.id)
        second = create_retention_operation(db, latest_run.id)
        assert first is not None
        assert second is not None
        assert first.id == second.id
        operation_id = str(first.id)

    partial = execute_retention_operation(operation_id, batch_size=10, max_rows=1)
    completed = execute_retention_operation(operation_id, batch_size=10, max_rows=10)
    repeated = execute_retention_operation(operation_id, batch_size=10, max_rows=10)

    with SessionLocal() as db:
        operation = db.get(RetentionOperation, first.id)
        remaining = db.scalar(select(func.count(ElementLocation.id)))

    assert partial.status == "pending"
    assert partial.deleted == 1
    assert completed.status == "succeeded"
    assert completed.deleted == 1
    assert repeated.status == "succeeded"
    assert repeated.deleted == 0
    assert operation is not None
    assert operation.rows_deleted == 2
    assert operation.batches_completed == 2
    assert operation.candidates_remaining == 0
    assert remaining == 1


def test_retention_waits_while_same_website_has_active_crawl() -> None:
    with SessionLocal() as db:
        website, url = _website_and_url(db)
        old_run, old_snapshot = _run_and_snapshot(db, website, url, 2024)
        latest_run, latest_snapshot = _run_and_snapshot(db, website, url, 2025)
        db.add_all(
            [
                _location(website, url, old_run, old_snapshot),
                _location(website, url, latest_run, latest_snapshot),
                CrawlJob(website_id=website.id, job_type="light_check", status="running"),
            ]
        )
        db.commit()
        operation = create_retention_operation(db, latest_run.id)
        assert operation is not None
        operation_id = str(operation.id)

    result = execute_retention_operation(operation_id)

    with SessionLocal() as db:
        remaining = db.scalar(select(func.count(ElementLocation.id)))
    assert result.status == "waiting_for_crawl"
    assert result.deleted == 0
    assert remaining == 2


def _website_and_url(db):  # type: ignore[no-untyped-def]
    website = Website(
        client=Client(name="Retention client"),
        name="Retention website",
        base_url="https://retention.test/",
    )
    db.add(website)
    db.flush()
    url = Url(website_id=website.id, normalized_url=website.base_url)
    db.add(url)
    db.flush()
    return website, url


def _run_and_snapshot(db, website, url, year):  # type: ignore[no-untyped-def]
    moment = datetime(year, 1, 1, tzinfo=UTC)
    job = CrawlJob(
        website_id=website.id,
        job_type="full_site_crawl",
        status="succeeded",
        finished_at=moment,
    )
    db.add(job)
    db.flush()
    run = CrawlRun(
        crawl_job_id=job.id,
        website_id=website.id,
        crawl_type="full_site_crawl",
        status="succeeded",
        started_at=moment,
        finished_at=moment,
    )
    db.add(run)
    db.flush()
    snapshot = UrlSnapshot(
        url_id=url.id,
        crawl_run_id=run.id,
        checked_at=moment,
        requested_url=url.normalized_url,
    )
    db.add(snapshot)
    db.flush()
    return run, snapshot


def _location(website, url, run, snapshot):  # type: ignore[no-untyped-def]
    return ElementLocation(
        website_id=website.id,
        source_url_id=url.id,
        snapshot_id=snapshot.id,
        crawl_run_id=run.id,
        issue_types=[],
        element_type="a",
        html_fragment="<a>Test</a>",
    )

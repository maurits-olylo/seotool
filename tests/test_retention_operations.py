from datetime import UTC, date, datetime

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, ElementLocation, UrlLink, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.integrations import SearchConsoleMetric
from app.models.issues import Issue, IssueOccurrence
from app.models.system import RetentionOperation
from app.models.website import Website
from app.services.retention_operations import (
    create_retention_operation,
    create_retention_operations,
    execute_retention_operation,
)
from app.services.retention_policy import AUTOMATIC_DATASETS, POLICY_VERSION


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


def test_retention_creates_idempotent_operation_per_automatic_dataset() -> None:
    with SessionLocal() as db:
        website, url = _website_and_url(db)
        latest_run, _ = _run_and_snapshot(db, website, url, 2026)

        first = create_retention_operations(db, latest_run.id)
        second = create_retention_operations(db, latest_run.id)

        assert len(first) == len(AUTOMATIC_DATASETS)
        assert {operation.dataset for operation in first} == set(AUTOMATIC_DATASETS)
        assert {operation.id for operation in first} == {operation.id for operation in second}
        assert {operation.policy_version for operation in first} == {POLICY_VERSION}


def test_daily_metric_retention_preserves_three_years_and_other_tenants() -> None:
    with SessionLocal() as db:
        website, url = _website_and_url(db)
        latest_run, _ = _run_and_snapshot(db, website, url, 2026)
        other_website = Website(
            client=Client(name="Other retention client"),
            name="Other retention website",
            base_url="https://other-retention.test/",
        )
        db.add(other_website)
        db.flush()
        db.add_all(
            [
                SearchConsoleMetric(
                    website_id=website.id,
                    date=date(2020, 1, 1),
                    page_url="https://retention.test/old",
                ),
                SearchConsoleMetric(
                    website_id=website.id,
                    date=date.today(),
                    page_url="https://retention.test/recent",
                ),
                SearchConsoleMetric(
                    website_id=other_website.id,
                    date=date(2020, 1, 1),
                    page_url="https://other-retention.test/old",
                ),
            ]
        )
        db.commit()
        operation = next(
            item
            for item in create_retention_operations(db, latest_run.id)
            if item.dataset == "search_console_metrics"
        )
        operation_id = str(operation.id)

    result = execute_retention_operation(operation_id, batch_size=10, max_rows=10)

    with SessionLocal() as db:
        own_dates = set(
            db.scalars(
                select(SearchConsoleMetric.date).where(
                    SearchConsoleMetric.website_id == website.id
                )
            )
        )
        other_count = db.scalar(
            select(func.count(SearchConsoleMetric.id)).where(
                SearchConsoleMetric.website_id == other_website.id
            )
        )
        stored = db.get(RetentionOperation, operation.id)

    assert result.status == "succeeded"
    assert result.dataset == "search_console_metrics"
    assert result.deleted == 1
    assert own_dates == {date.today()}
    assert other_count == 1
    assert stored is not None
    assert stored.before_report["policy_version"] == POLICY_VERSION
    assert stored.after_report["candidates_remaining"] == 0


def test_url_link_retention_preserves_latest_and_issue_evidence() -> None:
    with SessionLocal() as db:
        website, url = _website_and_url(db)
        unprotected_run, _ = _run_and_snapshot(db, website, url, 2020)
        unprotected_run.crawl_type = "light_check"
        evidence_run, evidence_snapshot = _run_and_snapshot(db, website, url, 2021)
        latest_run, _ = _run_and_snapshot(db, website, url, 2026)
        issue = Issue(
            website_id=website.id,
            url_id=url.id,
            issue_type="retention_test",
            category="internal_links",
            severity="low",
            title="Bewijs bewaren",
            description="Test",
            recommended_action="Test",
        )
        db.add(issue)
        db.flush()
        db.add(
            IssueOccurrence(
                issue_id=issue.id,
                crawl_run_id=evidence_run.id,
                snapshot_id=evidence_snapshot.id,
            )
        )
        db.add_all(
            [
                _link(url, unprotected_run, "https://retention.test/remove"),
                _link(url, evidence_run, "https://retention.test/evidence"),
                _link(url, latest_run, "https://retention.test/latest"),
            ]
        )
        db.commit()
        operation = next(
            item
            for item in create_retention_operations(db, latest_run.id)
            if item.dataset == "url_links"
        )
        operation_id = str(operation.id)

    result = execute_retention_operation(operation_id, batch_size=10, max_rows=10)

    with SessionLocal() as db:
        targets = set(db.scalars(select(UrlLink.target_url)))

    assert result.deleted == 1
    assert targets == {
        "https://retention.test/evidence",
        "https://retention.test/latest",
    }


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


def _link(url, run, target):  # type: ignore[no-untyped-def]
    return UrlLink(
        crawl_run_id=run.id,
        source_url_id=url.id,
        target_url=target,
        is_internal=True,
        is_nofollow=False,
    )

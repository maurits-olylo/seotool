from datetime import UTC, date, datetime

from sqlalchemy.orm import Session, sessionmaker

from app.db.session import engine
from app.models.client import Client
from app.models.crawl import CrawlRun, ElementLocation, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.integrations import SearchConsoleMetric, SearchConsoleQueryMetric
from app.models.website import Website
from app.services.crawl_deployment import start_deployment_drain
from app.services.retention_audit import build_retention_audit, cleanup_element_locations

SessionLocal = sessionmaker(bind=engine)


def test_retention_audit_protects_current_crawls_and_issue_evidence() -> None:
    with SessionLocal() as db:
        website, url = _website_and_url(db)
        old_run, old_snapshot = _run_and_snapshot(db, website, url, "succeeded", 2024)
        latest_run, latest_snapshot = _run_and_snapshot(db, website, url, "succeeded", 2025)
        active_run, active_snapshot = _run_and_snapshot(db, website, url, "running", 2026)
        light_run, light_snapshot = _run_and_snapshot(
            db, website, url, "succeeded", 2027, crawl_type="light_check"
        )

        db.add_all(
            [
                _location(website, url, old_run, old_snapshot, []),
                _location(website, url, old_run, old_snapshot, ["missing_h1"]),
                _location(website, url, latest_run, latest_snapshot, []),
                _location(website, url, active_run, active_snapshot, []),
                _location(website, url, light_run, light_snapshot, []),
            ]
        )
        db.commit()
        latest_run_id = latest_run.id
        active_run_id = active_run.id

        result = build_retention_audit(db, as_of=date(2026, 7, 25))

    website_result = result["websites"][0]
    assert result["mode"] == "read_only_dry_run"
    assert set(website_result["protected_crawl_run_ids"]) == {
        str(latest_run_id),
        str(active_run_id),
    }
    assert website_result["element_locations"] == {
        "total": 5,
        "protected_by_crawl_run": 2,
        "protected_as_latest_url_snapshot": 1,
        "protected_as_issue_evidence": 1,
        "cleanup_candidates": 1,
    }
    protected_runs = website_result["protected_crawl_runs"]
    assert {item["reasons"][0] for item in protected_runs} == {
        "active_crawl",
        "latest_completed_full_crawl",
    }


def test_retention_audit_reports_gsc_age_buckets_without_mutation() -> None:
    with SessionLocal() as db:
        website, _ = _website_and_url(db)
        for metric_date in (date(2026, 7, 1), date(2026, 4, 1), date(2025, 1, 1)):
            db.add(
                SearchConsoleMetric(
                    website_id=website.id,
                    date=metric_date,
                    page_url=f"https://example.com/{metric_date}",
                )
            )
            db.add(
                SearchConsoleQueryMetric(
                    website_id=website.id,
                    date=metric_date,
                    query=f"query-{metric_date}",
                    page_url="https://example.com/",
                )
            )
        db.commit()

        result = build_retention_audit(db, as_of=date(2026, 7, 25))
        remaining = db.query(SearchConsoleQueryMetric).count()

    buckets = result["websites"][0]["search_console_query_metrics"]
    assert buckets == {
        "total": 3,
        "last_90_days": 1,
        "days_91_to_180": 1,
        "older_than_180_days": 1,
    }
    assert remaining == 3


def test_element_location_cleanup_requires_safe_maintenance() -> None:
    with SessionLocal() as db:
        _website_and_url(db)
        db.commit()

        try:
            cleanup_element_locations(db)
        except RuntimeError as exc:
            assert "active=true" in str(exc)
        else:
            raise AssertionError("Opschoning had zonder maintenance moeten weigeren")


def test_element_location_cleanup_deletes_only_candidates_in_batches() -> None:
    progress: list[tuple[str, int, int]] = []
    with SessionLocal() as db:
        website, url = _website_and_url(db)
        old_run, old_snapshot = _run_and_snapshot(db, website, url, "succeeded", 2024)
        latest_run, latest_snapshot = _run_and_snapshot(db, website, url, "succeeded", 2025)
        db.add_all(
            [
                _location(website, url, old_run, old_snapshot, []),
                _location(website, url, old_run, old_snapshot, ["missing_h1"]),
                _location(website, url, latest_run, latest_snapshot, []),
            ]
        )
        db.commit()
        status = start_deployment_drain(db)
        assert status.safe

        result = cleanup_element_locations(
            db,
            batch_size=1,
            on_batch=lambda website_name, deleted, total: progress.append(
                (website_name, deleted, total)
            ),
        )
        remaining = db.query(ElementLocation).all()

    assert result.deleted == 1
    assert result.batches == 1
    assert result.websites == {"Audit website": 1}
    assert len(remaining) == 2
    assert any(item.issue_types == ["missing_h1"] for item in remaining)
    assert progress == [("Audit website", 1, 1)]


def _website_and_url(db: Session) -> tuple[Website, Url]:
    client = Client(name="Audit client")
    db.add(client)
    db.flush()
    website = Website(client_id=client.id, name="Audit website", base_url="https://example.com/")
    db.add(website)
    db.flush()
    url = Url(website_id=website.id, normalized_url="https://example.com/")
    db.add(url)
    db.flush()
    return website, url


def _run_and_snapshot(
    db: Session,
    website: Website,
    url: Url,
    status: str,
    year: int,
    *,
    crawl_type: str = "full_site_crawl",
) -> tuple[CrawlRun, UrlSnapshot]:
    moment = datetime(year, 1, 1, tzinfo=UTC)
    job = CrawlJob(website_id=website.id, job_type=crawl_type, status=status)
    db.add(job)
    db.flush()
    run = CrawlRun(
        crawl_job_id=job.id,
        website_id=website.id,
        crawl_type=crawl_type,
        status=status,
        started_at=moment,
        finished_at=moment if status == "succeeded" else None,
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


def _location(
    website: Website,
    url: Url,
    run: CrawlRun,
    snapshot: UrlSnapshot,
    issue_types: list[str],
) -> ElementLocation:
    return ElementLocation(
        website_id=website.id,
        source_url_id=url.id,
        snapshot_id=snapshot.id,
        crawl_run_id=run.id,
        issue_types=issue_types,
        element_type="a",
        html_fragment="<a>Test</a>",
    )

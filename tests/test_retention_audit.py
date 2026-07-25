from datetime import UTC, date, datetime

from sqlalchemy.orm import Session, sessionmaker

from app.db.session import engine
from app.models.client import Client
from app.models.crawl import CrawlRun, ElementLocation, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.integrations import SearchConsoleMetric, SearchConsoleQueryMetric
from app.models.website import Website
from app.services.retention_audit import build_retention_audit

SessionLocal = sessionmaker(bind=engine)


def test_retention_audit_protects_current_crawls_and_issue_evidence() -> None:
    with SessionLocal() as db:
        website, url = _website_and_url(db)
        old_run, old_snapshot = _run_and_snapshot(db, website, url, "succeeded", 2024)
        latest_run, latest_snapshot = _run_and_snapshot(db, website, url, "succeeded", 2025)
        active_run, active_snapshot = _run_and_snapshot(db, website, url, "running", 2026)

        db.add_all(
            [
                _location(website, url, old_run, old_snapshot, []),
                _location(website, url, old_run, old_snapshot, ["missing_h1"]),
                _location(website, url, latest_run, latest_snapshot, []),
                _location(website, url, active_run, active_snapshot, []),
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
        "total": 4,
        "protected_by_current_crawl": 2,
        "protected_as_issue_evidence": 1,
        "cleanup_candidates": 1,
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
    db: Session, website: Website, url: Url, status: str, year: int
) -> tuple[CrawlRun, UrlSnapshot]:
    moment = datetime(year, 1, 1, tzinfo=UTC)
    job = CrawlJob(website_id=website.id, job_type="full_site_crawl", status=status)
    db.add(job)
    db.flush()
    run = CrawlRun(
        crawl_job_id=job.id,
        website_id=website.id,
        crawl_type="full_site_crawl",
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

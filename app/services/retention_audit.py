from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, select, true
from sqlalchemy.orm import Session

from app.models.crawl import CrawlRun, ElementLocation
from app.models.integrations import SearchConsoleMetric, SearchConsoleQueryMetric
from app.models.website import Website

COMPLETED_FULL_CRAWL_STATUSES = {"succeeded", "partially_succeeded"}
ACTIVE_CRAWL_STATUSES = {"running", "paused", "pause_requested"}


@dataclass(frozen=True)
class ElementLocationAudit:
    total: int
    protected_by_crawl_run: int
    protected_as_latest_url_snapshot: int
    protected_as_issue_evidence: int
    cleanup_candidates: int


@dataclass(frozen=True)
class MetricAgeAudit:
    total: int
    last_90_days: int
    days_91_to_180: int
    older_than_180_days: int


def build_retention_audit(db: Session, *, as_of: date | None = None) -> dict[str, Any]:
    """Report retention candidates without changing database state."""
    audit_date = as_of or date.today()
    protected_runs = _protected_crawl_runs(db)
    websites = db.scalars(select(Website).order_by(Website.name, Website.id)).all()

    website_results = []
    for website in websites:
        website_runs = protected_runs.get(website.id, {})
        website_run_ids = set(website_runs)
        website_results.append(
            {
                "website": website.name,
                "website_id": str(website.id),
                "protected_crawl_run_ids": sorted(str(item) for item in website_run_ids),
                "protected_crawl_runs": sorted(
                    website_runs.values(), key=lambda item: item["started_at"], reverse=True
                ),
                "element_locations": asdict(
                    _element_location_audit(db, website.id, website_run_ids)
                ),
                "search_console_page_metrics": asdict(
                    _metric_age_audit(db, SearchConsoleMetric, website.id, audit_date)
                ),
                "search_console_query_metrics": asdict(
                    _metric_age_audit(db, SearchConsoleQueryMetric, website.id, audit_date)
                ),
            }
        )

    return {
        "mode": "read_only_dry_run",
        "as_of": audit_date.isoformat(),
        "retention_proposal": {
            "element_locations": (
                "Bewaar actieve crawls, de laatste geslaagde of gedeeltelijk geslaagde "
                "volledige crawl, de nieuwste locatiehoudende snapshot per URL en alle "
                "locaties met issues."
            ),
            "search_console_query_metrics": (
                "Leeftijdsmeting voor een mogelijke latere detailretentie van 180 dagen; "
                "deze audit verwijdert niets."
            ),
        },
        "websites": website_results,
        "totals": _sum_website_results(website_results),
    }


def _protected_crawl_runs(db: Session) -> dict[UUID, dict[UUID, dict[str, Any]]]:
    runs = db.execute(
        select(
            CrawlRun.id,
            CrawlRun.website_id,
            CrawlRun.crawl_type,
            CrawlRun.status,
            CrawlRun.finished_at,
            CrawlRun.started_at,
        ).order_by(CrawlRun.website_id, CrawlRun.started_at.desc())
    ).all()
    protected: dict[UUID, dict[UUID, dict[str, Any]]] = {}
    latest_full_found: set[UUID] = set()
    for run in runs:
        reasons = []
        if run.status in ACTIVE_CRAWL_STATUSES:
            reasons.append("active_crawl")
        if (
            run.website_id not in latest_full_found
            and run.crawl_type == "full_site_crawl"
            and run.status in COMPLETED_FULL_CRAWL_STATUSES
        ):
            reasons.append("latest_completed_full_crawl")
            latest_full_found.add(run.website_id)
        if reasons:
            protected.setdefault(run.website_id, {})[run.id] = {
                "crawl_run_id": str(run.id),
                "crawl_type": run.crawl_type,
                "status": run.status,
                "started_at": run.started_at.isoformat(),
                "reasons": reasons,
            }
    return protected


def _element_location_audit(
    db: Session, website_id: UUID, protected_run_ids: set[UUID]
) -> ElementLocationAudit:
    issue_count = func.json_array_length(ElementLocation.issue_types)
    protected_run_condition = (
        ElementLocation.crawl_run_id.in_(protected_run_ids)
        if protected_run_ids
        else ~true()
    )
    latest_snapshot_condition = ElementLocation.snapshot_id.in_(
        _latest_location_snapshot_ids(website_id)
    )
    protected_latest_condition = ~protected_run_condition & latest_snapshot_condition
    remaining_condition = ~protected_run_condition & ~latest_snapshot_condition
    row = db.execute(
        select(
            func.count(ElementLocation.id),
            func.sum(case((protected_run_condition, 1), else_=0)),
            func.sum(case((protected_latest_condition, 1), else_=0)),
            func.sum(
                case(
                    (remaining_condition & (issue_count > 0), 1),
                    else_=0,
                )
            ),
            func.sum(
                case(
                    (remaining_condition & (issue_count == 0), 1),
                    else_=0,
                )
            ),
        ).where(ElementLocation.website_id == website_id)
    ).one()
    return ElementLocationAudit(*(int(value or 0) for value in row))


def _latest_location_snapshot_ids(website_id: UUID):  # type: ignore[no-untyped-def]
    location_snapshots = (
        select(
            ElementLocation.source_url_id.label("source_url_id"),
            ElementLocation.snapshot_id.label("snapshot_id"),
            ElementLocation.crawl_run_id.label("crawl_run_id"),
        )
        .where(ElementLocation.website_id == website_id)
        .group_by(
            ElementLocation.source_url_id,
            ElementLocation.snapshot_id,
            ElementLocation.crawl_run_id,
        )
        .subquery()
    )
    ranked = (
        select(
            location_snapshots.c.snapshot_id,
            func.row_number()
            .over(
                partition_by=location_snapshots.c.source_url_id,
                order_by=(CrawlRun.started_at.desc(), location_snapshots.c.snapshot_id.desc()),
            )
            .label("position"),
        )
        .join(CrawlRun, CrawlRun.id == location_snapshots.c.crawl_run_id)
        .subquery()
    )
    return select(ranked.c.snapshot_id).where(ranked.c.position == 1)


def _metric_age_audit(
    db: Session,
    model: type[SearchConsoleMetric] | type[SearchConsoleQueryMetric],
    website_id: UUID,
    audit_date: date,
) -> MetricAgeAudit:
    day_90 = audit_date - timedelta(days=90)
    day_180 = audit_date - timedelta(days=180)
    row = db.execute(
        select(
            func.count(model.id),
            func.sum(case((model.date > day_90, 1), else_=0)),
            func.sum(case(((model.date > day_180) & (model.date <= day_90), 1), else_=0)),
            func.sum(case((model.date <= day_180, 1), else_=0)),
        ).where(model.website_id == website_id)
    ).one()
    return MetricAgeAudit(*(int(value or 0) for value in row))


def _sum_website_results(results: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    sections = (
        "element_locations",
        "search_console_page_metrics",
        "search_console_query_metrics",
    )
    totals: dict[str, dict[str, int]] = {}
    for section in sections:
        totals[section] = {}
        for result in results:
            for key, value in result[section].items():
                totals[section][key] = totals[section].get(key, 0) + value
    return totals

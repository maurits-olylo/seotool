from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import case, delete, func, select, true
from sqlalchemy.orm import Session

from app.models.crawl import CrawlRun, ElementLocation, UrlLink
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


@dataclass(frozen=True)
class UrlLinkAgeAudit:
    total: int
    last_90_days: int
    days_91_to_180: int
    older_than_180_days: int


@dataclass(frozen=True)
class ElementLocationCleanup:
    deleted: int
    batches: int
    websites: dict[str, int]
    limit_reached: bool


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
                "url_links": asdict(_url_link_age_audit(db, website.id, audit_date)),
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
            "url_links": (
                "Leeftijdsmeting per volledige crawl; een bewaarbeleid wordt pas ingevoerd nadat "
                "historie-, issue- en verificatiebewijs expliciet zijn beschermd."
            ),
        },
        "websites": website_results,
        "totals": _sum_website_results(website_results),
    }


def cleanup_element_locations(
    db: Session,
    *,
    batch_size: int = 10_000,
    website_id: UUID | None = None,
    max_rows: int = 50_000,
    on_batch: Callable[[str, int, int], None] | None = None,
) -> ElementLocationCleanup:
    """Delete audited element-location candidates in bounded transactions."""
    if batch_size < 1 or batch_size > 50_000:
        raise ValueError("batch_size moet tussen 1 en 50000 liggen")
    if max_rows < 1 or max_rows > 1_000_000:
        raise ValueError("max_rows moet tussen 1 en 1000000 liggen")
    _require_safe_maintenance(db)

    protected_runs = _protected_crawl_runs(db)
    website_query = select(Website).order_by(Website.name, Website.id)
    if website_id is not None:
        website_query = website_query.where(Website.id == website_id)
    websites = db.scalars(website_query).all()
    deleted_by_website: dict[str, int] = {}
    total_deleted = 0
    batches = 0
    limit_reached = False

    for website in websites:
        protected_run_ids = set(protected_runs.get(website.id, {}))
        latest_snapshot_ids = tuple(db.scalars(_latest_location_snapshot_ids(website.id)).all())
        issue_count = func.json_array_length(ElementLocation.issue_types)
        last_id: UUID | None = None
        website_deleted = 0

        while True:
            _require_safe_maintenance(db)
            remaining_capacity = max_rows - total_deleted
            if remaining_capacity <= 0:
                limit_reached = True
                break
            conditions = [
                ElementLocation.website_id == website.id,
                issue_count == 0,
                ~ElementLocation.snapshot_id.in_(latest_snapshot_ids),
            ]
            if protected_run_ids:
                conditions.append(~ElementLocation.crawl_run_id.in_(protected_run_ids))
            if last_id is not None:
                conditions.append(ElementLocation.id > last_id)
            ids = tuple(
                db.scalars(
                    select(ElementLocation.id)
                    .where(*conditions)
                    .order_by(ElementLocation.id)
                    .limit(min(batch_size, remaining_capacity))
                ).all()
            )
            if not ids:
                break

            db.execute(delete(ElementLocation).where(ElementLocation.id.in_(ids)))
            db.commit()
            last_id = ids[-1]
            batch_deleted = len(ids)
            website_deleted += batch_deleted
            total_deleted += batch_deleted
            batches += 1
            if on_batch is not None:
                on_batch(website.name, batch_deleted, total_deleted)

        deleted_by_website[website.name] = website_deleted
        if limit_reached:
            break

    return ElementLocationCleanup(
        deleted=total_deleted,
        batches=batches,
        websites=deleted_by_website,
        limit_reached=limit_reached,
    )


def _require_safe_maintenance(db: Session) -> None:
    from app.services.crawl_deployment import deployment_drain_status

    status = deployment_drain_status(db)
    if not status.active or not status.safe:
        raise RuntimeError(
            "Elementlocaties kunnen alleen worden opgeschoond wanneer maintenance active=true "
            "en safe=true is."
        )


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
        ElementLocation.crawl_run_id.in_(protected_run_ids) if protected_run_ids else ~true()
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


def _url_link_age_audit(
    db: Session,
    website_id: UUID,
    audit_date: date,
) -> UrlLinkAgeAudit:
    day_90 = datetime.combine(audit_date - timedelta(days=90), time.min, tzinfo=UTC)
    day_180 = datetime.combine(audit_date - timedelta(days=180), time.min, tzinfo=UTC)
    row = db.execute(
        select(
            func.count(UrlLink.id),
            func.sum(case((CrawlRun.started_at > day_90, 1), else_=0)),
            func.sum(
                case(
                    (
                        (CrawlRun.started_at > day_180) & (CrawlRun.started_at <= day_90),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.sum(case((CrawlRun.started_at <= day_180, 1), else_=0)),
        )
        .select_from(UrlLink)
        .join(CrawlRun, CrawlRun.id == UrlLink.crawl_run_id)
        .where(CrawlRun.website_id == website_id)
    ).one()
    return UrlLinkAgeAudit(*(int(value or 0) for value in row))


def _sum_website_results(results: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    sections = (
        "element_locations",
        "search_console_page_metrics",
        "search_console_query_metrics",
        "url_links",
    )
    totals: dict[str, dict[str, int]] = {}
    for section in sections:
        totals[section] = {}
        for result in results:
            for key, value in result[section].items():
                totals[section][key] = totals[section].get(key, 0) + value
    return totals

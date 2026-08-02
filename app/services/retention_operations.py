from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

import structlog
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.common import utc_now
from app.models.crawl import CrawlRun, ElementLocation, UrlLink
from app.models.discovery import CrawlJob
from app.models.integrations import (
    BingPageMetric,
    BingQueryMetric,
    GoogleAnalyticsEventMetric,
    GoogleAnalyticsLandingPageEventMetric,
    GoogleAnalyticsMetric,
    SearchConsoleMetric,
    SearchConsoleQueryMetric,
)
from app.models.system import RetentionOperation
from app.models.website import Website
from app.services.retention_audit import (
    COMPLETED_FULL_CRAWL_STATUSES,
    element_location_candidate_ids,
)
from app.services.retention_policy import AUTOMATIC_DATASETS, POLICIES, POLICY_VERSION

logger = structlog.get_logger()
ACTIVE_CRAWL_STATUSES = (
    "waiting_for_capacity",
    "pending",
    "running",
    "pause_requested",
    "paused",
    "cancel_requested",
)
RETRY_DELAY = timedelta(minutes=10)
RUNNING_TIMEOUT = timedelta(hours=1)
DATE_MODELS = {
    "search_console_metrics": SearchConsoleMetric,
    "search_console_query_metrics": SearchConsoleQueryMetric,
    "google_analytics_metrics": GoogleAnalyticsMetric,
    "google_analytics_event_metrics": GoogleAnalyticsEventMetric,
    "google_analytics_landing_page_event_metrics": GoogleAnalyticsLandingPageEventMetric,
    "bing_page_metrics": BingPageMetric,
    "bing_query_metrics": BingQueryMetric,
}


@dataclass(frozen=True)
class RetentionRunResult:
    operation_id: str
    dataset: str
    status: str
    deleted: int
    batches: int
    candidates_remaining: int | None


def create_retention_operation(db: Session, crawl_run_id: UUID) -> RetentionOperation | None:
    """Compatibility helper for the original element-location operation."""
    return _create_retention_operation(db, crawl_run_id, "element_locations")


def create_retention_operations(db: Session, crawl_run_id: UUID) -> list[RetentionOperation]:
    """Create one idempotent operation per automatic dataset."""
    operations = []
    for dataset in AUTOMATIC_DATASETS:
        operation = _create_retention_operation(db, crawl_run_id, dataset)
        if operation is not None:
            operations.append(operation)
    return operations


def _create_retention_operation(
    db: Session,
    crawl_run_id: UUID,
    dataset: str,
) -> RetentionOperation | None:
    run = db.get(CrawlRun, crawl_run_id)
    if (
        run is None
        or run.crawl_type != "full_site_crawl"
        or run.status not in COMPLETED_FULL_CRAWL_STATUSES
    ):
        return None
    existing = db.scalar(
        select(RetentionOperation).where(
            RetentionOperation.trigger_crawl_run_id == crawl_run_id,
            RetentionOperation.dataset == dataset,
        )
    )
    if existing is not None:
        return existing
    operation = RetentionOperation(
        website_id=run.website_id,
        trigger_crawl_run_id=run.id,
        dataset=dataset,
        policy_version=POLICY_VERSION,
        status="pending",
        next_attempt_at=utc_now(),
    )
    db.add(operation)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return db.scalar(
            select(RetentionOperation).where(
                RetentionOperation.trigger_crawl_run_id == crawl_run_id,
                RetentionOperation.dataset == dataset,
            )
        )
    db.refresh(operation)
    return operation


def execute_retention_operation(
    operation_id: str,
    *,
    batch_size: int = 10_000,
    max_rows: int = 50_000,
) -> RetentionRunResult:
    """Run bounded, idempotent batches and persist progress after every commit."""
    if batch_size < 1 or batch_size > 50_000:
        raise ValueError("batch_size must be between 1 and 50000")
    if max_rows < 1 or max_rows > 1_000_000:
        raise ValueError("max_rows must be between 1 and 1000000")

    operation_uuid = uuid.UUID(operation_id)
    deleted_this_run = 0
    batches_this_run = 0
    try:
        while deleted_this_run < max_rows:
            with SessionLocal() as db:
                operation = db.scalar(
                    select(RetentionOperation)
                    .where(RetentionOperation.id == operation_uuid)
                    .with_for_update()
                )
                if operation is None:
                    raise RuntimeError("Retention operation does not exist")
                if operation.status == "succeeded":
                    return _result(operation, deleted_this_run, batches_this_run)
                website = db.scalar(
                    select(Website).where(Website.id == operation.website_id).with_for_update()
                )
                if website is None:
                    raise RuntimeError("Retention website does not exist")
                active_crawl = db.scalar(
                    select(CrawlJob.id).where(
                        CrawlJob.website_id == operation.website_id,
                        CrawlJob.status.in_(ACTIVE_CRAWL_STATUSES),
                    )
                )
                if active_crawl is not None:
                    operation.status = "waiting_for_crawl"
                    operation.next_attempt_at = utc_now() + RETRY_DELAY
                    operation.error_message = None
                    db.commit()
                    return _result(operation, deleted_this_run, batches_this_run)

                operation.status = "running"
                operation.started_at = operation.started_at or utc_now()
                operation.attempt_count += 1 if batches_this_run == 0 else 0
                operation.error_message = None
                operation.next_attempt_at = utc_now() + RUNNING_TIMEOUT
                ids = _candidate_ids(
                    db,
                    operation.dataset,
                    operation.website_id,
                    limit=min(batch_size, max_rows - deleted_this_run),
                )
                if not operation.before_report:
                    operation.before_report = {
                        "dataset": operation.dataset,
                        "policy_version": operation.policy_version,
                        "first_batch_candidates": len(ids),
                        "measured_at": utc_now().isoformat(),
                    }
                if not ids:
                    operation.status = "succeeded"
                    operation.candidates_remaining = 0
                    operation.finished_at = utc_now()
                    operation.next_attempt_at = None
                    operation.after_report = {
                        "dataset": operation.dataset,
                        "policy_version": operation.policy_version,
                        "rows_deleted": operation.rows_deleted,
                        "candidates_remaining": 0,
                        "measured_at": utc_now().isoformat(),
                    }
                    db.commit()
                    logger.info(
                        "retention_operation_succeeded",
                        operation_id=operation_id,
                        website_id=str(operation.website_id),
                        dataset=operation.dataset,
                        rows_deleted=operation.rows_deleted,
                        batches_completed=operation.batches_completed,
                    )
                    return _result(operation, deleted_this_run, batches_this_run)

                model = _dataset_model(operation.dataset)
                db.execute(delete(model).where(model.id.in_(ids)))
                batch_deleted = len(ids)
                operation.rows_deleted += batch_deleted
                operation.batches_completed += 1
                operation.candidates_remaining = None
                operation.next_attempt_at = utc_now() + RUNNING_TIMEOUT
                db.commit()
                deleted_this_run += batch_deleted
                batches_this_run += 1
                logger.info(
                    "retention_batch_completed",
                    operation_id=operation_id,
                    website_id=str(operation.website_id),
                    dataset=operation.dataset,
                    batch_deleted=batch_deleted,
                    total_deleted=operation.rows_deleted,
                )

        with SessionLocal() as db:
            operation = db.get(RetentionOperation, operation_uuid)
            if operation is None:
                raise RuntimeError("Retention operation does not exist")
            operation.status = "pending"
            operation.next_attempt_at = utc_now() + RETRY_DELAY
            db.commit()
            logger.warning(
                "retention_operation_limit_reached",
                operation_id=operation_id,
                website_id=str(operation.website_id),
                dataset=operation.dataset,
                deleted_this_run=deleted_this_run,
                rows_deleted=operation.rows_deleted,
            )
            return _result(operation, deleted_this_run, batches_this_run)
    except Exception as exc:
        with SessionLocal() as db:
            operation = db.get(RetentionOperation, operation_uuid)
            if operation is not None:
                operation.status = "failed"
                operation.error_message = str(exc)[:4000]
                operation.next_attempt_at = datetime.now(UTC) + RETRY_DELAY
                db.commit()
        logger.exception("retention_operation_failed", operation_id=operation_id)
        raise


def _candidate_ids(
    db: Session,
    dataset: str,
    website_id: UUID,
    *,
    limit: int,
) -> tuple[UUID, ...]:
    if dataset == "element_locations":
        return element_location_candidate_ids(db, website_id, limit=limit)
    policy = POLICIES.get(dataset)
    if policy is None or not policy.automatic_cleanup or policy.retain_days is None:
        raise RuntimeError(f"Dataset {dataset!r} heeft geen automatisch retentiebeleid")
    cutoff_date = date.today() - timedelta(days=policy.retain_days)
    if dataset == "url_links":
        cutoff = datetime.combine(cutoff_date, time.min, tzinfo=UTC)
        statement = (
            select(UrlLink.id)
            .join(CrawlRun, CrawlRun.id == UrlLink.crawl_run_id)
            .where(CrawlRun.website_id == website_id, CrawlRun.started_at < cutoff)
            .order_by(UrlLink.id)
            .limit(limit)
        )
        protected_runs = _protected_evidence_run_ids(db, website_id)
        if protected_runs:
            statement = statement.where(~UrlLink.crawl_run_id.in_(protected_runs))
        return tuple(db.scalars(statement).all())
    model = DATE_MODELS.get(dataset)
    if model is None:
        raise RuntimeError(f"Onbekende retentiedataset: {dataset}")
    return tuple(
        db.scalars(
            select(model.id)
            .where(model.website_id == website_id, model.date < cutoff_date)
            .order_by(model.id)
            .limit(limit)
        ).all()
    )


def _protected_evidence_run_ids(db: Session, website_id: UUID) -> set[UUID]:
    from app.models.issues import Issue, IssueOccurrence
    from app.models.recommendations import RecommendationTask, RecommendationVerification

    protected = set(
        db.scalars(
            select(CrawlRun.id).where(
                CrawlRun.website_id == website_id,
                CrawlRun.status.in_(["running", "paused", "pause_requested"]),
            )
        )
    )
    latest_full = db.scalar(
        select(CrawlRun.id)
        .where(
            CrawlRun.website_id == website_id,
            CrawlRun.crawl_type == "full_site_crawl",
            CrawlRun.status.in_(COMPLETED_FULL_CRAWL_STATUSES),
        )
        .order_by(CrawlRun.started_at.desc())
        .limit(1)
    )
    if latest_full:
        protected.add(latest_full)
    protected.update(
        db.scalars(
            select(IssueOccurrence.crawl_run_id)
            .join(Issue, Issue.id == IssueOccurrence.issue_id)
            .where(Issue.website_id == website_id)
        )
    )
    protected.update(
        db.scalars(
            select(CrawlRun.id)
            .join(
                RecommendationVerification,
                RecommendationVerification.crawl_job_id == CrawlRun.crawl_job_id,
            )
            .join(
                RecommendationTask,
                RecommendationTask.id == RecommendationVerification.task_id,
            )
            .where(RecommendationTask.website_id == website_id)
        )
    )
    return protected


def _dataset_model(dataset: str):  # type: ignore[no-untyped-def]
    if dataset == "element_locations":
        return ElementLocation
    if dataset == "url_links":
        return UrlLink
    model = DATE_MODELS.get(dataset)
    if model is None:
        raise RuntimeError(f"Onbekende retentiedataset: {dataset}")
    return model


def _result(operation: RetentionOperation, deleted: int, batches: int) -> RetentionRunResult:
    return RetentionRunResult(
        operation_id=str(operation.id),
        dataset=operation.dataset,
        status=operation.status,
        deleted=deleted,
        batches=batches,
        candidates_remaining=operation.candidates_remaining,
    )

import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models.sensor import SensorDailyPageMetric, SensorManifest, SensorMeasurementState
from app.services.behavioral_provider import (
    BehavioralAggregateProvider,
    BehavioralCapabilities,
    BehavioralPageAggregate,
)

MINIMUM_RELIABLE_DAYS = 7
MINIMUM_PAGE_COVERAGE = 0.9
MAXIMUM_FRESHNESS_LAG_DAYS = 2


class SensorAggregateProvider(BehavioralAggregateProvider):
    capabilities = BehavioralCapabilities(
        page_sessions=True,
        outcomes=True,
        element_exposure=True,
        element_interaction=True,
        process_states=True,
        active_time=True,
        trusted_outcomes=True,
    )

    def __init__(self, db: Session):
        self.db = db

    def page_aggregates_between(
        self,
        website_id: UUID,
        period_start: date,
        period_end: date,
    ) -> list[BehavioralPageAggregate]:
        rows = self.db.execute(
            select(
                SensorDailyPageMetric.url_id,
                func.sum(SensorDailyPageMetric.page_sessions),
                func.sum(SensorDailyPageMetric.exposures),
                func.sum(SensorDailyPageMetric.interactions),
                func.sum(SensorDailyPageMetric.process_starts),
                func.sum(SensorDailyPageMetric.observed_outcomes),
                func.sum(SensorDailyPageMetric.trusted_outcomes),
            )
            .where(
                SensorDailyPageMetric.website_id == website_id,
                SensorDailyPageMetric.date.between(period_start, period_end),
            )
            .group_by(SensorDailyPageMetric.url_id)
        )
        return [
            BehavioralPageAggregate(
                url_id=url_id,
                period_start=period_start,
                period_end=period_end,
                page_sessions=int(page_sessions or 0),
                exposures=int(exposures or 0),
                interactions=int(interactions or 0),
                process_starts=int(process_starts or 0),
                observed_outcomes=int(observed_outcomes or 0),
                trusted_outcomes=int(trusted_outcomes or 0),
            )
            for (
                url_id,
                page_sessions,
                exposures,
                interactions,
                process_starts,
                observed_outcomes,
                trusted_outcomes,
            ) in rows
        ]


def reconcile_sensor_measurement_state(
    db: Session,
    website_id: UUID,
    period_start: date,
    period_end: date,
    *,
    expected_pages: int,
    client_version: str = "1.0.0",
    schema_version: str = "1",
) -> SensorMeasurementState:
    if period_end < period_start:
        raise ValueError("Sensor period end must be on or after its start")
    if expected_pages < 0:
        raise ValueError("Expected Sensor pages cannot be negative")
    period_start_at = datetime.combine(period_start, time.min, tzinfo=UTC)
    period_end_at = datetime.combine(period_end, time.max, tzinfo=UTC)
    manifest = db.scalar(
        select(SensorManifest)
        .where(
            SensorManifest.website_id == website_id,
            SensorManifest.status == "active",
            SensorManifest.valid_from <= period_end_at,
            SensorManifest.expires_at >= period_start_at,
        )
        .order_by(SensorManifest.valid_from.desc())
        .limit(1)
    )
    metrics = list(
        db.scalars(
            select(SensorDailyPageMetric).where(
                SensorDailyPageMetric.website_id == website_id,
                SensorDailyPageMetric.date.between(period_start, period_end),
            )
        )
    )
    observed_pages = len({metric.url_id for metric in metrics})
    observed_days = len({metric.date for metric in metrics})
    rejected_count = sum(metric.rejected_count for metric in metrics)
    sampled_count = sum(metric.sampled_count for metric in metrics)
    starts = sum(metric.process_starts for metric in metrics)
    observed_outcomes = sum(metric.observed_outcomes for metric in metrics)
    trusted_outcomes = sum(metric.trusted_outcomes for metric in metrics)
    latest_date = max((metric.date for metric in metrics), default=None)
    page_coverage = observed_pages / expected_pages if expected_pages else 0.0

    checks: list[dict[str, object]] = [
        {"name": "manifest_configured", "passed": manifest is not None},
        {
            "name": "page_coverage",
            "passed": page_coverage >= MINIMUM_PAGE_COVERAGE,
            "observed": round(page_coverage, 4),
        },
        {"name": "minimum_days", "passed": observed_days >= MINIMUM_RELIABLE_DAYS},
        {"name": "no_rejections", "passed": rejected_count == 0},
        {"name": "possible_outcome_order", "passed": observed_outcomes <= starts},
    ]
    if manifest is None:
        status = "not_configured"
    elif latest_date is not None and latest_date < period_end - timedelta(
        days=MAXIMUM_FRESHNESS_LAG_DAYS
    ):
        status = "stale"
    elif (
        rejected_count
        or observed_outcomes > starts
        or (metrics and page_coverage < MINIMUM_PAGE_COVERAGE)
    ):
        status = "attention_needed"
    elif observed_days >= MINIMUM_RELIABLE_DAYS and page_coverage >= MINIMUM_PAGE_COVERAGE:
        status = "reliable"
    else:
        status = "provisional"

    first_date = min((metric.date for metric in metrics), default=None)
    payload = {
        "manifest": manifest.manifest_version if manifest else None,
        "period": [period_start.isoformat(), period_end.isoformat()],
        "expected_pages": expected_pages,
        "metrics": [
            [
                str(metric.id),
                metric.date.isoformat(),
                metric.page_sessions,
                metric.exposures,
                metric.interactions,
                metric.process_starts,
                metric.observed_outcomes,
                metric.trusted_outcomes,
                metric.rejected_count,
                metric.sampled_count,
            ]
            for metric in sorted(metrics, key=lambda item: (item.date, str(item.id)))
        ],
    }
    input_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    existing = db.scalar(
        select(SensorMeasurementState).where(
            SensorMeasurementState.website_id == website_id,
            SensorMeasurementState.period_start == period_start,
            SensorMeasurementState.period_end == period_end,
            SensorMeasurementState.input_hash == input_hash,
        )
    )
    if existing:
        return existing
    state = SensorMeasurementState(
        website_id=website_id,
        period_start=period_start,
        period_end=period_end,
        status=status,
        client_version=client_version if manifest else None,
        schema_version=schema_version if manifest else None,
        manifest_version=manifest.manifest_version if manifest else None,
        first_observation_at=(
            datetime.combine(first_date, time.min, tzinfo=UTC) if first_date else None
        ),
        last_observation_at=(
            datetime.combine(latest_date, time.max, tzinfo=UTC) if latest_date else None
        ),
        expected_pages=expected_pages,
        observed_pages=observed_pages,
        rejected_count=rejected_count,
        sampled_count=sampled_count,
        outcome_evidence={"observed": observed_outcomes, "trusted": trusted_outcomes},
        checks=checks,
        input_hash=input_hash,
    )
    db.add(state)
    db.flush()
    return state


def reliable_sensor_evidence_by_url(
    db: Session, website_id: UUID, period_start: date, period_end: date
) -> dict[UUID, dict[str, object]]:
    latest = db.scalar(
        select(SensorMeasurementState)
        .where(
            SensorMeasurementState.website_id == website_id,
            SensorMeasurementState.period_start <= period_start,
            SensorMeasurementState.period_end >= period_end,
        )
        .order_by(SensorMeasurementState.created_at.desc())
        .limit(1)
    )
    if latest is None or latest.status != "reliable":
        return {}
    result: dict[UUID, dict[str, object]] = {}
    for aggregate in SensorAggregateProvider(db).page_aggregates_between(
        website_id, period_start, period_end
    ):
        sessions = int(aggregate.page_sessions or 0)
        interactions = int(aggregate.interactions or 0)
        outcomes = int(aggregate.observed_outcomes or 0) + int(aggregate.trusted_outcomes or 0)
        result[aggregate.url_id] = {
            "page_sessions": sessions,
            "exposures": int(aggregate.exposures or 0),
            "interactions": interactions,
            "process_starts": int(aggregate.process_starts or 0),
            "outcomes": outcomes,
            "interaction_rate": round(interactions / sessions, 4) if sessions else None,
            "outcome_rate": round(outcomes / sessions, 4) if sessions else None,
        }
    return result


def sensor_totals(
    db: Session,
    website_id: UUID,
    url_ids: list[UUID],
    period_start: date,
    period_end: date,
) -> dict[str, float | int]:
    if not url_ids:
        return {
            "days": 0,
            "page_sessions": 0,
            "interactions": 0,
            "process_starts": 0,
            "outcomes": 0,
        }
    sessions, interactions, starts, observed, trusted, days = db.execute(
        select(
            func.sum(SensorDailyPageMetric.page_sessions),
            func.sum(SensorDailyPageMetric.interactions),
            func.sum(SensorDailyPageMetric.process_starts),
            func.sum(SensorDailyPageMetric.observed_outcomes),
            func.sum(SensorDailyPageMetric.trusted_outcomes),
            func.count(distinct(SensorDailyPageMetric.date)),
        ).where(
            SensorDailyPageMetric.website_id == website_id,
            SensorDailyPageMetric.url_id.in_(url_ids),
            SensorDailyPageMetric.date.between(period_start, period_end),
        )
    ).one()
    return {
        "days": int(days or 0),
        "page_sessions": int(sessions or 0),
        "interactions": int(interactions or 0),
        "process_starts": int(starts or 0),
        "outcomes": int(observed or 0) + int(trusted or 0),
    }

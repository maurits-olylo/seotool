import hashlib
import json
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models.effects import EffectEvaluation, EffectIntervention
from app.models.integrations import GoogleAnalyticsMetric, MatomoPageMetric, SearchConsoleMetric
from app.services.analytics_provider import primary_analytics_source

METHOD_VERSION = "1"
PERIOD_DAYS = 28
MINIMUM_MATURITY_DAYS = 42
MINIMUM_COVERAGE_DAYS = 14


def evaluate_effect_cohort(
    db: Session,
    website_id: UUID,
    change_period_start: date,
    change_period_end: date,
    *,
    as_of: date | None = None,
) -> EffectEvaluation:
    if change_period_end < change_period_start:
        raise ValueError("Change period end must be on or after its start")
    as_of = as_of or datetime.now(UTC).date()
    interventions = list(
        db.scalars(
            select(EffectIntervention)
            .where(
                EffectIntervention.website_id == website_id,
                EffectIntervention.implemented_at
                >= datetime.combine(change_period_start, time.min, tzinfo=UTC),
                EffectIntervention.implemented_at
                <= datetime.combine(change_period_end, time.max, tzinfo=UTC),
            )
            .order_by(EffectIntervention.implemented_at, EffectIntervention.id)
        )
    )
    url_counts = Counter(
        str(item["url_id"])
        for intervention in interventions
        for item in intervention.url_context
        if item.get("url_id")
    )
    url_ids = sorted(UUID(value) for value in url_counts)
    earliest = min(
        (item.implemented_at.date() for item in interventions), default=change_period_start
    )
    latest = max((item.implemented_at.date() for item in interventions), default=change_period_end)
    baseline_end = earliest - timedelta(days=1)
    baseline_start = baseline_end - timedelta(days=PERIOD_DAYS - 1)
    observation_end = as_of
    observation_start = observation_end - timedelta(days=PERIOD_DAYS - 1)

    gsc_before = _gsc_totals(db, website_id, url_ids, baseline_start, baseline_end)
    gsc_after = _gsc_totals(db, website_id, url_ids, observation_start, observation_end)
    analytics_source = primary_analytics_source(db, website_id)
    analytics_before = _analytics_totals(
        db, website_id, url_ids, baseline_start, baseline_end, analytics_source
    )
    analytics_after = _analytics_totals(
        db, website_id, url_ids, observation_start, observation_end, analytics_source
    )
    metrics = {
        "gsc": _comparison(gsc_before, gsc_after),
        "analytics": _comparison(analytics_before, analytics_after),
    }
    if not interventions:
        status = "insufficient_data"
    elif latest + timedelta(days=MINIMUM_MATURITY_DAYS) > as_of:
        status = "too_early"
    elif gsc_before["days"] < MINIMUM_COVERAGE_DAYS or gsc_after["days"] < MINIMUM_COVERAGE_DAYS:
        status = "insufficient_data"
    else:
        status = "development_visible"

    coverage = {
        "gsc": {
            "baseline_days": gsc_before["days"],
            "observation_days": gsc_after["days"],
            "expected_days": PERIOD_DAYS,
        },
        "analytics": {
            "source": analytics_source,
            "baseline_days": analytics_before["days"],
            "observation_days": analytics_after["days"],
            "expected_days": PERIOD_DAYS,
        },
    }
    confidence = {
        "mature": bool(interventions) and latest + timedelta(days=MINIMUM_MATURITY_DAYS) <= as_of,
        "gsc_comparable": bool(
            gsc_before["days"] >= MINIMUM_COVERAGE_DAYS
            and gsc_after["days"] >= MINIMUM_COVERAGE_DAYS
        ),
        "analytics_comparable": bool(analytics_before["days"] and analytics_after["days"]),
        "overlapping_urls": sum(1 for count in url_counts.values() if count > 1),
    }
    payload = {
        "method": METHOD_VERSION,
        "periods": [
            change_period_start.isoformat(),
            change_period_end.isoformat(),
            baseline_start.isoformat(),
            baseline_end.isoformat(),
            observation_start.isoformat(),
            observation_end.isoformat(),
        ],
        "interventions": [item.input_hash for item in interventions],
        "metrics": metrics,
        "coverage": coverage,
    }
    input_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    existing = db.scalar(
        select(EffectEvaluation).where(
            EffectEvaluation.website_id == website_id,
            EffectEvaluation.input_hash == input_hash,
            EffectEvaluation.method_version == METHOD_VERSION,
        )
    )
    if existing:
        return existing
    evaluation = EffectEvaluation(
        website_id=website_id,
        change_period_start=change_period_start,
        change_period_end=change_period_end,
        baseline_start=baseline_start,
        baseline_end=baseline_end,
        observation_start=observation_start,
        observation_end=observation_end,
        method_version=METHOD_VERSION,
        input_hash=input_hash,
        status=status,
        analytics_source=analytics_source,
        intervention_ids=[str(item.id) for item in interventions],
        url_ids=[str(item) for item in url_ids],
        metrics=metrics,
        source_coverage=coverage,
        confidence_factors=confidence,
        evidence=[
            {
                "basis": "observed_correlation",
                "message": "KPI-ontwikkeling is waargenomen; causaliteit is niet bewezen.",
            }
        ],
    )
    db.add(evaluation)
    db.flush()
    return evaluation


def _gsc_totals(
    db: Session, website_id: UUID, url_ids: list[UUID], start: date, end: date
) -> dict[str, float | int]:
    if not url_ids:
        return {"days": 0, "clicks": 0.0, "impressions": 0, "ctr": 0.0, "position": 0.0}
    clicks, impressions, weighted_position, days = db.execute(
        select(
            func.sum(SearchConsoleMetric.clicks),
            func.sum(SearchConsoleMetric.impressions),
            func.sum(SearchConsoleMetric.position * SearchConsoleMetric.impressions),
            func.count(distinct(SearchConsoleMetric.date)),
        ).where(
            SearchConsoleMetric.website_id == website_id,
            SearchConsoleMetric.url_id.in_(url_ids),
            SearchConsoleMetric.date.between(start, end),
        )
    ).one()
    impressions = int(impressions or 0)
    clicks = float(clicks or 0)
    return {
        "days": int(days or 0),
        "clicks": clicks,
        "impressions": impressions,
        "ctr": clicks / impressions if impressions else 0.0,
        "position": float(weighted_position or 0) / impressions if impressions else 0.0,
    }


def _analytics_totals(
    db: Session,
    website_id: UUID,
    url_ids: list[UUID],
    start: date,
    end: date,
    source: str | None,
) -> dict[str, float | int]:
    if not url_ids or source not in {"ga4", "matomo"}:
        return {"days": 0, "visits": 0, "users": 0, "conversions": 0.0}
    model = GoogleAnalyticsMetric if source == "ga4" else MatomoPageMetric
    visits = model.sessions if source == "ga4" else model.visits
    users = model.active_users if source == "ga4" else model.unique_pageviews
    conversions = model.key_events if source == "ga4" else model.conversions
    total_visits, total_users, total_conversions, days = db.execute(
        select(
            func.sum(visits),
            func.sum(users),
            func.sum(conversions),
            func.count(distinct(model.date)),
        ).where(
            model.website_id == website_id,
            model.url_id.in_(url_ids),
            model.date.between(start, end),
        )
    ).one()
    return {
        "days": int(days or 0),
        "visits": int(total_visits or 0),
        "users": int(total_users or 0),
        "conversions": float(total_conversions or 0),
    }


def _comparison(
    baseline: dict[str, float | int], observation: dict[str, float | int]
) -> dict[str, object]:
    result: dict[str, object] = {"baseline": baseline, "observation": observation, "changes": {}}
    changes: dict[str, object] = {}
    for key, before in baseline.items():
        if key == "days":
            continue
        after = observation[key]
        changes[key] = {
            "absolute": round(float(after) - float(before), 6),
            "relative_percent": (
                round((float(after) - float(before)) / float(before) * 100, 2)
                if float(before)
                else None
            ),
        }
    result["changes"] = changes
    return result

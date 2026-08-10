import hashlib
import json
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models.effects import EffectEvaluation, EffectIntervention
from app.models.integrations import (
    GoogleAnalyticsMetric,
    MatomoPageMetric,
    SearchConsoleMetric,
    SearchConsoleQueryMetric,
)
from app.services.analytics_provider import primary_analytics_source
from app.services.content_analysis import normalize_query
from app.services.sensor_aggregates import sensor_totals

METHOD_VERSION = "3"
PERIOD_DAYS = 28
MINIMUM_MATURITY_DAYS = 42
MINIMUM_COVERAGE_DAYS = 14
INSUFFICIENT_DATA_RETRY_DAYS = 7
VISIBLE_EFFECT_REFRESH_DAYS = 28


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
    question_scopes = sorted(
        {
            (UUID(str(context["url_id"])), normalize_query(str(question)))
            for intervention in interventions
            for question in [intervention.task_snapshot.get("question")]
            if isinstance(question, str) and question.strip()
            for context in intervention.url_context
            if context.get("url_id")
        },
        key=lambda item: (str(item[0]), item[1]),
    )
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
    question_gsc_before = _gsc_question_totals(
        db, website_id, question_scopes, baseline_start, baseline_end
    )
    question_gsc_after = _gsc_question_totals(
        db, website_id, question_scopes, observation_start, observation_end
    )
    analytics_source = primary_analytics_source(db, website_id)
    analytics_before = _analytics_totals(
        db, website_id, url_ids, baseline_start, baseline_end, analytics_source
    )
    analytics_after = _analytics_totals(
        db, website_id, url_ids, observation_start, observation_end, analytics_source
    )
    sensor_before = sensor_totals(db, website_id, url_ids, baseline_start, baseline_end)
    sensor_after = sensor_totals(db, website_id, url_ids, observation_start, observation_end)
    metrics = {
        "gsc": _comparison(gsc_before, gsc_after),
        "question_gsc": _comparison(question_gsc_before, question_gsc_after),
        "analytics": _comparison(analytics_before, analytics_after),
        "behavior_observation": _comparison(sensor_before, sensor_after),
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
        "question_gsc": {
            "scope_count": len(question_scopes),
            "baseline_days": question_gsc_before["days"],
            "observation_days": question_gsc_after["days"],
            "expected_days": PERIOD_DAYS,
        },
        "analytics": {
            "source": analytics_source,
            "baseline_days": analytics_before["days"],
            "observation_days": analytics_after["days"],
            "expected_days": PERIOD_DAYS,
        },
        "behavior_observation": {
            "baseline_days": sensor_before["days"],
            "observation_days": sensor_after["days"],
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
        "behavior_observation_comparable": bool(sensor_before["days"] and sensor_after["days"]),
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


def refresh_due_effect_evaluations(db: Session, *, as_of: date | None = None) -> int:
    """Refresh intervention cohorts only when a meaningful recheck is due."""
    as_of = as_of or datetime.now(UTC).date()
    refreshed = 0
    interventions = list(
        db.scalars(select(EffectIntervention).order_by(EffectIntervention.implemented_at))
    )
    for intervention in interventions:
        change_date = intervention.implemented_at.date()
        latest = db.scalar(
            select(EffectEvaluation)
            .where(
                EffectEvaluation.website_id == intervention.website_id,
                EffectEvaluation.change_period_start == change_date,
                EffectEvaluation.change_period_end == change_date,
            )
            .order_by(EffectEvaluation.created_at.desc())
            .limit(1)
        )
        if not _effect_recheck_due(latest, change_date, as_of):
            continue
        evaluate_effect_cohort(
            db,
            intervention.website_id,
            change_date,
            change_date,
            as_of=as_of,
        )
        refreshed += 1
    return refreshed


def _effect_recheck_due(latest: EffectEvaluation | None, change_date: date, as_of: date) -> bool:
    if latest is None:
        return True
    created_date = latest.created_at.date()
    if latest.status == "too_early":
        return as_of >= change_date + timedelta(days=MINIMUM_MATURITY_DAYS)
    if latest.status in {"insufficient_data", "not_comparable"}:
        return as_of >= created_date + timedelta(days=INSUFFICIENT_DATA_RETRY_DAYS)
    return as_of >= created_date + timedelta(days=VISIBLE_EFFECT_REFRESH_DAYS)


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


def _gsc_question_totals(
    db: Session,
    website_id: UUID,
    scopes: list[tuple[UUID, str]],
    start: date,
    end: date,
) -> dict[str, float | int]:
    if not scopes:
        return {"days": 0, "clicks": 0.0, "impressions": 0, "ctr": 0.0, "position": 0.0}
    allowed = set(scopes)
    rows = db.execute(
        select(
            SearchConsoleQueryMetric.url_id,
            SearchConsoleQueryMetric.query,
            SearchConsoleQueryMetric.date,
            SearchConsoleQueryMetric.clicks,
            SearchConsoleQueryMetric.impressions,
            SearchConsoleQueryMetric.position,
        ).where(
            SearchConsoleQueryMetric.website_id == website_id,
            SearchConsoleQueryMetric.url_id.in_({url_id for url_id, _question in scopes}),
            SearchConsoleQueryMetric.date.between(start, end),
        )
    )
    clicks = 0.0
    impressions = 0
    weighted_position = 0.0
    days: set[date] = set()
    for url_id, query, metric_date, row_clicks, row_impressions, position in rows:
        if (url_id, normalize_query(str(query))) not in allowed:
            continue
        row_impressions = int(row_impressions or 0)
        clicks += float(row_clicks or 0)
        impressions += row_impressions
        weighted_position += float(position or 0) * row_impressions
        days.add(metric_date)
    return {
        "days": len(days),
        "clicks": clicks,
        "impressions": impressions,
        "ctr": clicks / impressions if impressions else 0.0,
        "position": weighted_position / impressions if impressions else 0.0,
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

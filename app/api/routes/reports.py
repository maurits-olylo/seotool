from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.models.integrations import (
    GoogleAnalyticsEventMetric,
    GoogleAnalyticsMetric,
    SearchConsoleMetric,
    WebsiteIntegration,
)
from app.models.issues import ActivityLog, Change, Issue
from app.services.authorization import require_website_access

router = APIRouter(tags=["reports"])
Period = Literal["month", "quarter", "half_year", "year", "ytd"]
ACTIVE_STATUSES = {"new", "review", "accepted", "planned", "in_progress", "waiting_for_client"}


def _period_dates(period: Period, end: date) -> tuple[date, date, date, date]:
    days = {"month": 30, "quarter": 90, "half_year": 182, "year": 365}
    start = date(end.year, 1, 1) if period == "ytd" else end - timedelta(days=days[period] - 1)
    length = (end - start).days + 1
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=length - 1)
    return start, end, previous_start, previous_end


def _delta(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


def _totals(
    daily: dict[date, dict[str, float]], start: date, end: date
) -> dict[str, float]:
    result: dict[str, float] = defaultdict(float)
    weighted_position = 0.0
    for metric_date, values in daily.items():
        if start <= metric_date <= end:
            for key, value in values.items():
                if key != "position_weight":
                    result[key] += value
            weighted_position += values.get("position_weight", 0)
    impressions = result.get("impressions", 0)
    if impressions:
        result["average_position"] = round(weighted_position / impressions, 1)
    return {key: round(value, 1) for key, value in result.items()}


def _issue_summary(issue: Issue) -> dict[str, object]:
    return {
        "id": str(issue.id),
        "title": issue.title,
        "issue_type": issue.issue_type,
        "category": issue.category,
        "severity": issue.severity,
        "status": issue.status,
        "recommended_action": issue.recommended_action,
        "first_detected_at": issue.first_detected_at,
    }


@router.get("/websites/{website_id}/client-report")
def client_report(
    website_id: UUID,
    period: Period = Query(default="month"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    require_website_access(db, principal, website_id)
    end = date.today() - timedelta(days=1)
    start, _, previous_start, previous_end = _period_dates(period, end)
    daily: dict[date, dict[str, float]] = defaultdict(dict)
    gsc_dates: list[date] = []
    ga_dates: list[date] = []
    key_event_dates: list[date] = []

    for metric_date, clicks, impressions, position_weight in db.execute(
        select(
            SearchConsoleMetric.date,
            func.sum(SearchConsoleMetric.clicks),
            func.sum(SearchConsoleMetric.impressions),
            func.sum(SearchConsoleMetric.position * SearchConsoleMetric.impressions),
        )
        .where(SearchConsoleMetric.website_id == website_id)
        .group_by(SearchConsoleMetric.date)
    ):
        gsc_dates.append(metric_date)
        daily[metric_date].update(
            clicks=float(clicks or 0),
            impressions=float(impressions or 0),
            position_weight=float(position_weight or 0),
        )
    for metric_date, sessions, users in db.execute(
        select(
            GoogleAnalyticsMetric.date,
            func.sum(GoogleAnalyticsMetric.sessions),
            func.sum(GoogleAnalyticsMetric.active_users),
        )
        .where(GoogleAnalyticsMetric.website_id == website_id)
        .group_by(GoogleAnalyticsMetric.date)
    ):
        ga_dates.append(metric_date)
        daily[metric_date].update(
            sessions=float(sessions or 0),
            active_users=float(users or 0),
        )

    ga4_mapping = db.scalar(
        select(WebsiteIntegration).where(
            WebsiteIntegration.website_id == website_id,
            WebsiteIntegration.service == "ga4",
        )
    )
    qualified_events = (
        set(ga4_mapping.settings.get("qualified_key_events", [])) if ga4_mapping else set()
    )
    event_breakdown: dict[str, float] = defaultdict(float)
    if qualified_events:
        for metric_date, event_name, events in db.execute(
            select(
                GoogleAnalyticsEventMetric.date,
                GoogleAnalyticsEventMetric.event_name,
                func.sum(GoogleAnalyticsEventMetric.key_events),
            )
            .where(
                GoogleAnalyticsEventMetric.website_id == website_id,
                GoogleAnalyticsEventMetric.event_name.in_(qualified_events),
            )
            .group_by(GoogleAnalyticsEventMetric.date, GoogleAnalyticsEventMetric.event_name)
        ):
            value = float(events or 0)
            key_event_dates.append(metric_date)
            daily[metric_date]["key_events"] = daily[metric_date].get("key_events", 0) + value
            if start <= metric_date <= end:
                event_breakdown[event_name] += value

    current = _totals(daily, start, end)
    previous = _totals(daily, previous_start, previous_end)
    comparisons: dict[str, float | None] = {}
    for key in {"clicks", "impressions", "sessions", "active_users", "key_events"}:
        source_dates = (
            gsc_dates
            if key in {"clicks", "impressions"}
            else key_event_dates
            if key == "key_events"
            else ga_dates
        )
        comparisons[key] = (
            _delta(float(current.get(key, 0)), float(previous.get(key, 0)))
            if source_dates and min(source_dates) <= previous_start
            else None
        )

    monthly: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for metric_date, values in daily.items():
        if metric_date >= end - timedelta(days=395):
            bucket = monthly[metric_date.strftime("%Y-%m")]
            for key in ("clicks", "impressions", "sessions", "active_users", "key_events"):
                bucket[key] += values.get(key, 0)

    start_at = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
    change_counts = {
        change_type: count
        for change_type, count in db.execute(
            select(Change.change_type, func.count(Change.id))
            .where(Change.website_id == website_id, Change.detected_at >= start_at)
            .group_by(Change.change_type)
            .order_by(func.count(Change.id).desc())
        )
    }
    completed = db.scalar(
        select(func.count(Issue.id)).where(
            Issue.website_id == website_id,
            (Issue.resolved_at >= start_at) | (Issue.verified_at >= start_at),
        )
    ) or 0
    activities = list(
        db.scalars(
            select(ActivityLog)
            .where(ActivityLog.website_id == website_id, ActivityLog.occurred_at >= start_at)
            .order_by(ActivityLog.occurred_at.desc())
            .limit(20)
        )
    )
    planned = list(
        db.scalars(
            select(Issue)
            .where(
                Issue.website_id == website_id,
                Issue.status.in_(["planned", "in_progress", "waiting_for_client"]),
            )
            .order_by(Issue.due_date.asc().nullslast(), Issue.severity)
            .limit(10)
        )
    )
    new_issues = list(
        db.scalars(
            select(Issue)
            .where(
                Issue.website_id == website_id,
                Issue.first_detected_at >= start_at,
                Issue.status.in_(ACTIVE_STATUSES),
            )
            .order_by(
                case(
                    (
                        Issue.issue_type.in_(
                            [
                                "http_404",
                                "internally_linked_404",
                                "expired_job_posting",
                                "thin_content",
                            ]
                        ),
                        0,
                    ),
                    else_=1,
                ),
                Issue.first_detected_at.desc(),
            )
            .limit(10)
        )
    )
    return {
        "period": period,
        "start_date": start,
        "end_date": end,
        "previous_start_date": previous_start,
        "previous_end_date": previous_end,
        "current": current,
        "previous": previous,
        "comparisons": comparisons,
        "monthly": [
            {"month": month, **{key: round(value, 1) for key, value in values.items()}}
            for month, values in sorted(monthly.items())
        ],
        "coverage": {
            "from": min(daily) if daily else None,
            "through": max(daily) if daily else None,
            "gsc_from": min(gsc_dates) if gsc_dates else None,
            "ga4_from": min(ga_dates) if ga_dates else None,
            "key_events_from": min(key_event_dates) if key_event_dates else None,
        },
        "qualified_key_events": {
            "configured": bool(qualified_events),
            "events": [
                {"event_name": name, "key_events": round(total, 1)}
                for name, total in sorted(
                    event_breakdown.items(), key=lambda item: item[1], reverse=True
                )
            ],
        },
        "work_completed": {
            "technically_verified": completed,
            "activities": [
                {
                    "summary": activity.summary,
                    "actor": activity.actor,
                    "occurred_at": activity.occurred_at,
                }
                for activity in activities
            ],
            "changes": change_counts,
        },
        "planned": [_issue_summary(issue) for issue in planned],
        "new_issues": [_issue_summary(issue) for issue in new_issues],
    }

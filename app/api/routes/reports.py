from calendar import monthrange
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
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
from app.models.reporting import MonthlyReportSnapshot
from app.services.authorization import require_website_access
from app.services.search_insights import build_search_insights

router = APIRouter(tags=["reports"])
Period = Literal["month", "quarter", "half_year", "year", "ytd"]
ACTIVE_STATUSES = {"new", "review", "accepted", "planned", "in_progress", "waiting_for_client"}
REPORT_PERIODS: tuple[Period, ...] = ("month", "quarter", "half_year", "ytd", "year")


def _shift_months(value: date, months: int) -> date:
    raw_month = value.month - 1 + months
    year = value.year + raw_month // 12
    month = raw_month % 12 + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def _period_dates(period: Period, end: date) -> tuple[date, date, date, date]:
    """Return a current window and the explicitly comparable reference window."""
    if period == "month":
        start = end - timedelta(days=29)
        previous_start, previous_end = _shift_months(start, -1), _shift_months(end, -1)
    elif period == "quarter":
        start = end - timedelta(days=89)
        previous_start, previous_end = _shift_months(start, -3), _shift_months(end, -3)
    elif period == "half_year":
        start = end - timedelta(days=181)
        previous_start, previous_end = _shift_months(start, -12), _shift_months(end, -12)
    elif period == "year":
        start = _shift_months(end, -12) + timedelta(days=1)
        previous_start, previous_end = _shift_months(start, -12), _shift_months(end, -12)
    else:  # YTD
        start = date(end.year, 1, 1)
        previous_start = date(end.year - 1, 1, 1)
        previous_end = _shift_months(end, -12)
    return start, end, previous_start, previous_end


def _comparison_context(period: str) -> str:
    labels = {
        "month": "dezelfde dagen in de vorige maand",
        "quarter": "dezelfde dagen in het vorige kwartaal",
        "half_year": "dezelfde zes maanden vorig jaar",
        "year": "de voorgaande twaalf maanden",
        "ytd": "dezelfde dagen vorig jaar",
        "monthly_snapshot": "de voorgaande kalendermaand",
    }
    return labels.get(period, "de voorafgaande vergelijkbare periode")


def _delta(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


def _available_periods(end: date, source_dates: list[date]) -> list[Period]:
    """Only offer periods that have a complete preceding comparison window."""
    if not source_dates:
        return []
    first_date = min(source_dates)
    available: list[Period] = []
    for period in REPORT_PERIODS:
        _, _, previous_start, _ = _period_dates(period, end)
        if first_date <= previous_start:
            available.append(period)
    return available


def _totals(daily: dict[date, dict[str, float]], start: date, end: date) -> dict[str, float]:
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


def build_client_report(
    website_id: UUID,
    period: str,
    start: date,
    end: date,
    previous_start: date,
    previous_end: date,
    db: Session,
) -> dict[str, object]:
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

    primary_metric = (
        "key_events"
        if qualified_events and key_event_dates
        else "sessions"
        if ga_dates
        else "clicks"
    )
    primary_source_dates = (
        key_event_dates
        if primary_metric == "key_events"
        else ga_dates
        if primary_metric == "sessions"
        else gsc_dates
    )
    comparison_source_dates = ga_dates or gsc_dates
    available_periods = _available_periods(end, comparison_source_dates)
    # A yearly headline must also be supportable by its primary KPI. Otherwise it
    # would fall back to an unrelated total (for example conversions only).
    if "year" in available_periods and "year" not in _available_periods(end, primary_source_dates):
        available_periods.remove("year")

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
    completed = (
        db.scalar(
            select(func.count(Issue.id)).where(
                Issue.website_id == website_id,
                (Issue.resolved_at >= start_at) | (Issue.verified_at >= start_at),
            )
        )
        or 0
    )
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
        "comparison_context": _comparison_context(period),
        "current": current,
        "previous": previous,
        "comparisons": comparisons,
        "primary_metric": primary_metric,
        "available_periods": available_periods,
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
        "search_insights": build_search_insights(
            db, website_id, start, end, previous_start, previous_end
        ),
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
    return build_client_report(
        website_id,
        period,
        start,
        end,
        previous_start,
        previous_end,
        db,
    )


@router.get("/websites/{website_id}/monthly-reports")
def list_monthly_reports(
    website_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> list[dict[str, object]]:
    require_website_access(db, principal, website_id)
    snapshots = list(
        db.scalars(
            select(MonthlyReportSnapshot)
            .where(MonthlyReportSnapshot.website_id == website_id)
            .order_by(MonthlyReportSnapshot.period_start.desc())
            .limit(36)
        )
    )
    return [
        {
            "id": str(snapshot.id),
            "period_start": snapshot.period_start,
            "period_end": snapshot.period_end,
            "generated_at": snapshot.generated_at,
        }
        for snapshot in snapshots
    ]


@router.get("/websites/{website_id}/monthly-reports/{snapshot_id}")
def get_monthly_report(
    website_id: UUID,
    snapshot_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    require_website_access(db, principal, website_id)
    snapshot = db.scalar(
        select(MonthlyReportSnapshot).where(
            MonthlyReportSnapshot.id == snapshot_id,
            MonthlyReportSnapshot.website_id == website_id,
        )
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail="Maandrapportage niet gevonden")
    return snapshot.report_data

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.common import utc_now
from app.models.integrations import (
    GoogleAnalyticsLandingPageEventMetric,
    GoogleAnalyticsMetric,
    WebsiteIntegration,
)
from app.models.issues import ActivityLog, Issue
from app.services.analytics_provider import (
    AnalyticsPageTotal,
    analytics_page_totals_between,
    primary_analytics_source,
)

MINIMUM_ANOMALOUS_EVENTS = 10
MINIMUM_EVENTS_PER_SESSION = 3
ANALYTICS_QUALITY_ISSUE_TYPE = "ga4_event_session_anomaly"


@dataclass(frozen=True)
class AnalyticsAnomaly:
    date: date
    url_id: UUID
    event_name: str
    events: float
    sessions: int


@dataclass(frozen=True)
class QualityAwareAnalyticsTotals:
    source: str | None
    rows: list[AnalyticsPageTotal]
    configured: bool
    anomalies: list[AnalyticsAnomaly]

    @property
    def suspicious_conversions(self) -> float:
        return sum(item.events for item in self.anomalies)


def quality_aware_analytics_totals(
    db: Session, website_id: UUID, period_start: date, period_end: date
) -> QualityAwareAnalyticsTotals:
    source = primary_analytics_source(db, website_id)
    if source == "matomo":
        _source, rows = analytics_page_totals_between(db, website_id, period_start, period_end)
        return QualityAwareAnalyticsTotals(source, rows, True, [])
    if source != "ga4":
        return QualityAwareAnalyticsTotals(source, [], False, [])

    mapping = db.scalar(
        select(WebsiteIntegration).where(
            WebsiteIntegration.website_id == website_id,
            WebsiteIntegration.service == "ga4",
            WebsiteIntegration.status == "active",
        )
    )
    selected_events = sorted(
        str(value)
        for value in (mapping.settings.get("qualified_key_events", []) if mapping else [])
        if value
    )
    if not selected_events:
        return QualityAwareAnalyticsTotals(source, [], False, [])

    session_rows = list(
        db.execute(
            select(
                GoogleAnalyticsMetric.url_id,
                func.sum(GoogleAnalyticsMetric.sessions),
                func.sum(GoogleAnalyticsMetric.active_users),
            )
            .where(
                GoogleAnalyticsMetric.website_id == website_id,
                GoogleAnalyticsMetric.date >= period_start,
                GoogleAnalyticsMetric.date <= period_end,
                GoogleAnalyticsMetric.url_id.is_not(None),
            )
            .group_by(GoogleAnalyticsMetric.url_id)
        )
    )
    conversions = dict(
        db.execute(
            select(
                GoogleAnalyticsLandingPageEventMetric.url_id,
                func.sum(GoogleAnalyticsLandingPageEventMetric.key_events),
            )
            .where(
                GoogleAnalyticsLandingPageEventMetric.website_id == website_id,
                GoogleAnalyticsLandingPageEventMetric.date >= period_start,
                GoogleAnalyticsLandingPageEventMetric.date <= period_end,
                GoogleAnalyticsLandingPageEventMetric.event_name.in_(selected_events),
                GoogleAnalyticsLandingPageEventMetric.url_id.is_not(None),
            )
            .group_by(GoogleAnalyticsLandingPageEventMetric.url_id)
        ).all()
    )
    rows = [
        AnalyticsPageTotal(
            url_id=url_id,
            visits=int(sessions or 0),
            users=int(users or 0),
            conversions=float(conversions.get(url_id, 0) or 0),
        )
        for url_id, sessions, users in session_rows
    ]
    return QualityAwareAnalyticsTotals(
        source,
        rows,
        True,
        _find_ga4_anomalies(db, website_id, period_start, period_end, selected_events),
    )


def _find_ga4_anomalies(
    db: Session,
    website_id: UUID,
    period_start: date,
    period_end: date,
    selected_events: list[str],
) -> list[AnalyticsAnomaly]:
    sessions = {
        (metric_date, url_id): int(value or 0)
        for metric_date, url_id, value in db.execute(
            select(
                GoogleAnalyticsMetric.date,
                GoogleAnalyticsMetric.url_id,
                func.sum(GoogleAnalyticsMetric.sessions),
            )
            .where(
                GoogleAnalyticsMetric.website_id == website_id,
                GoogleAnalyticsMetric.date >= period_start,
                GoogleAnalyticsMetric.date <= period_end,
                GoogleAnalyticsMetric.url_id.is_not(None),
            )
            .group_by(GoogleAnalyticsMetric.date, GoogleAnalyticsMetric.url_id)
        )
    }
    anomalies = []
    for metric_date, url_id, event_name, events in db.execute(
        select(
            GoogleAnalyticsLandingPageEventMetric.date,
            GoogleAnalyticsLandingPageEventMetric.url_id,
            GoogleAnalyticsLandingPageEventMetric.event_name,
            func.sum(GoogleAnalyticsLandingPageEventMetric.key_events),
        )
        .where(
            GoogleAnalyticsLandingPageEventMetric.website_id == website_id,
            GoogleAnalyticsLandingPageEventMetric.date >= period_start,
            GoogleAnalyticsLandingPageEventMetric.date <= period_end,
            GoogleAnalyticsLandingPageEventMetric.event_name.in_(selected_events),
            GoogleAnalyticsLandingPageEventMetric.url_id.is_not(None),
        )
        .group_by(
            GoogleAnalyticsLandingPageEventMetric.date,
            GoogleAnalyticsLandingPageEventMetric.url_id,
            GoogleAnalyticsLandingPageEventMetric.event_name,
        )
    ):
        event_count = float(events or 0)
        session_count = sessions.get((metric_date, url_id), 0)
        if event_count >= MINIMUM_ANOMALOUS_EVENTS and (
            session_count == 0 or event_count / session_count >= MINIMUM_EVENTS_PER_SESSION
        ):
            anomalies.append(
                AnalyticsAnomaly(
                    date=metric_date,
                    url_id=url_id,
                    event_name=event_name,
                    events=event_count,
                    sessions=session_count,
                )
            )
    return sorted(anomalies, key=lambda item: (-item.events, item.date, str(item.url_id)))


def reconcile_ga4_quality_issues(
    db: Session, website_id: UUID, period_start: date, period_end: date
) -> dict[str, int]:
    """Persist GA4 anomalies through the normal two-clean-check issue lifecycle."""
    totals = quality_aware_analytics_totals(db, website_id, period_start, period_end)
    if totals.source != "ga4" or not totals.configured:
        return {"anomalies": 0, "created": 0, "resolved": 0, "verified": 0}

    anomalies_by_url: dict[UUID, list[AnalyticsAnomaly]] = {}
    for anomaly in totals.anomalies:
        anomalies_by_url.setdefault(anomaly.url_id, []).append(anomaly)
    checked_url_ids = {row.url_id for row in totals.rows} | set(anomalies_by_url)
    existing = {
        issue.url_id: issue
        for issue in db.scalars(
            select(Issue).where(
                Issue.website_id == website_id,
                Issue.issue_type == ANALYTICS_QUALITY_ISSUE_TYPE,
            )
        )
        if issue.url_id in checked_url_ids
    }
    now = utc_now()
    created = resolved = verified = 0
    for url_id in sorted(checked_url_ids, key=str):
        anomalies = anomalies_by_url.get(url_id, [])
        issue = existing.get(url_id)
        if anomalies:
            if issue is None:
                issue = Issue(
                    website_id=website_id,
                    url_id=url_id,
                    issue_type=ANALYTICS_QUALITY_ISSUE_TYPE,
                    category="analytics_quality",
                    severity="high",
                    confidence="high",
                    status="new",
                    title="GA4-leadevents wijken sterk af van sessies",
                    description=(
                        "Gekwalificeerde events zijn niet aannemelijk in verhouding tot "
                        "organische sessies."
                    ),
                    recommended_action=(
                        "Controleer eventtrigger, consent, dubbele tags en de gekoppelde "
                        "landingspagina; valideer daarna opnieuw."
                    ),
                )
                db.add(issue)
                db.flush()
                created += 1
            else:
                issue.last_detected_at = now
                if issue.status in {"resolved", "verified", "ignored"}:
                    issue.status = "new"
                    issue.resolved_at = None
                    issue.verified_at = None
            _record_quality_check(
                db, issue, period_start, period_end, anomalies, "attention_needed"
            )
        elif issue is not None and issue.status not in {"ignored", "accepted_risk", "verified"}:
            if issue.status == "resolved":
                issue.status = "verified"
                issue.verified_at = now
                verified += 1
                outcome = "verified"
            else:
                issue.status = "resolved"
                issue.resolved_at = now
                resolved += 1
                outcome = "resolved"
            _record_quality_check(db, issue, period_start, period_end, [], outcome)
    return {
        "anomalies": len(totals.anomalies),
        "created": created,
        "resolved": resolved,
        "verified": verified,
    }


def _record_quality_check(
    db: Session,
    issue: Issue,
    period_start: date,
    period_end: date,
    anomalies: list[AnalyticsAnomaly],
    outcome: str,
) -> None:
    db.add(
        ActivityLog(
            website_id=issue.website_id,
            activity_type="analytics_quality_checked",
            summary=f"GA4-meetkwaliteit: {outcome}",
            details={
                "issue_id": str(issue.id),
                "outcome": outcome,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "anomalies": [
                    {
                        "date": item.date.isoformat(),
                        "url_id": str(item.url_id),
                        "event_name": item.event_name,
                        "events": item.events,
                        "sessions": item.sessions,
                    }
                    for item in anomalies
                ],
            },
        )
    )

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.integrations import (
    GoogleAnalyticsLandingPageEventMetric,
    GoogleAnalyticsMetric,
    WebsiteIntegration,
)
from app.services.analytics_provider import (
    AnalyticsPageTotal,
    analytics_page_totals_between,
    primary_analytics_source,
)

MINIMUM_ANOMALOUS_EVENTS = 10
MINIMUM_EVENTS_PER_SESSION = 3


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

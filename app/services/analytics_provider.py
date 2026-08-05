from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.integrations import GoogleAnalyticsMetric, MatomoPageMetric
from app.models.website import WebsiteSettings


@dataclass(frozen=True)
class AnalyticsPageTotal:
    url_id: UUID
    visits: int
    users: int
    conversions: float


def primary_analytics_source(db: Session, website_id: UUID) -> str | None:
    settings = db.get(WebsiteSettings, website_id)
    return settings.primary_analytics_source if settings else None


def analytics_page_totals(
    db: Session, website_id: UUID, since: date
) -> tuple[str | None, list[AnalyticsPageTotal]]:
    source = primary_analytics_source(db, website_id)
    if source == "ga4":
        rows = db.execute(
            select(
                GoogleAnalyticsMetric.url_id,
                func.sum(GoogleAnalyticsMetric.sessions),
                func.sum(GoogleAnalyticsMetric.active_users),
                func.sum(GoogleAnalyticsMetric.key_events),
            )
            .where(
                GoogleAnalyticsMetric.website_id == website_id,
                GoogleAnalyticsMetric.date >= since,
                GoogleAnalyticsMetric.url_id.is_not(None),
            )
            .group_by(GoogleAnalyticsMetric.url_id)
        )
    elif source == "matomo":
        rows = db.execute(
            select(
                MatomoPageMetric.url_id,
                func.sum(MatomoPageMetric.visits),
                func.sum(MatomoPageMetric.unique_pageviews),
                func.sum(MatomoPageMetric.conversions),
            )
            .where(
                MatomoPageMetric.website_id == website_id,
                MatomoPageMetric.date >= since,
                MatomoPageMetric.url_id.is_not(None),
            )
            .group_by(MatomoPageMetric.url_id)
        )
    else:
        return None, []
    return source, [
        AnalyticsPageTotal(
            url_id=url_id,
            visits=int(visits or 0),
            users=int(users or 0),
            conversions=float(conversions or 0),
        )
        for url_id, visits, users, conversions in rows
    ]

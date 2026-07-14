from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.discovery import Url
from app.models.integrations import GoogleAnalyticsMetric, SearchConsoleMetric
from app.services.content_intent_insights import build_content_intent_insights
from app.services.search_insights import build_search_insights


@dataclass
class PagePerformance:
    clicks: float = 0
    impressions: int = 0


@dataclass
class LandingPagePerformance:
    sessions: int = 0
    key_events: float = 0
    url_id: UUID | None = None

    @property
    def conversion_rate(self) -> float:
        return self.key_events / self.sessions if self.sessions else 0


def _url_map(db: Session, url_ids: set[UUID]) -> dict[UUID, str]:
    if not url_ids:
        return {}
    rows = db.execute(select(Url.id, Url.normalized_url).where(Url.id.in_(url_ids))).all()
    return dict(rows)


def _page_declines(
    db: Session,
    website_id: UUID,
    start: date,
    end: date,
    previous_start: date,
    previous_end: date,
) -> list[dict[str, object]]:
    current: dict[str, PagePerformance] = defaultdict(PagePerformance)
    previous: dict[str, PagePerformance] = defaultdict(PagePerformance)
    rows = db.execute(
        select(
            SearchConsoleMetric.date,
            SearchConsoleMetric.page_url,
            SearchConsoleMetric.clicks,
            SearchConsoleMetric.impressions,
        ).where(
            SearchConsoleMetric.website_id == website_id,
            SearchConsoleMetric.date >= previous_start,
            SearchConsoleMetric.date <= end,
        )
    )
    for metric_date, page_url, clicks, impressions in rows:
        target = current if start <= metric_date <= end else previous
        totals = target[str(page_url)]
        totals.clicks += float(clicks or 0)
        totals.impressions += int(impressions or 0)

    candidates: list[tuple[float, str, PagePerformance, PagePerformance]] = []
    for page_url, old in previous.items():
        new = current[page_url]
        clicks_declined = old.clicks >= 20 and new.clicks <= old.clicks * 0.75
        impressions_declined = old.impressions >= 500 and new.impressions <= old.impressions * 0.75
        if clicks_declined or impressions_declined:
            lost_clicks = old.clicks - new.clicks
            lost_impressions = old.impressions - new.impressions
            candidates.append((lost_clicks * 1000 + lost_impressions, page_url, old, new))

    result = []
    for _, page_url, old, new in sorted(candidates, reverse=True)[:5]:
        click_change = (
            round((new.clicks - old.clicks) / old.clicks * 100, 1) if old.clicks else None
        )
        impression_change = (
            round((new.impressions - old.impressions) / old.impressions * 100, 1)
            if old.impressions
            else None
        )
        result.append(
            {
                "type": "declining_page",
                "source": "Google Search Console",
                "title": "Landingspagina verliest organische zichtbaarheid",
                "description": (
                    f"Klikken: {old.clicks:,.0f} → {new.clicks:,.0f}; "
                    f"vertoningen: {old.impressions:,} → {new.impressions:,}."
                ),
                "url": page_url,
                "previous_clicks": round(old.clicks, 1),
                "clicks": round(new.clicks, 1),
                "click_change_percent": click_change,
                "previous_impressions": old.impressions,
                "impressions": new.impressions,
                "impression_change_percent": impression_change,
            }
        )
    return result


def _conversion_opportunities(
    db: Session,
    website_id: UUID,
    start: date,
    end: date,
) -> list[dict[str, object]]:
    pages: dict[str, LandingPagePerformance] = defaultdict(LandingPagePerformance)
    rows = db.execute(
        select(
            GoogleAnalyticsMetric.landing_page,
            GoogleAnalyticsMetric.url_id,
            GoogleAnalyticsMetric.sessions,
            GoogleAnalyticsMetric.key_events,
        ).where(
            GoogleAnalyticsMetric.website_id == website_id,
            GoogleAnalyticsMetric.date >= start,
            GoogleAnalyticsMetric.date <= end,
        )
    )
    for landing_page, url_id, sessions, key_events in rows:
        if not landing_page or str(landing_page) == "(not set)":
            continue
        totals = pages[str(landing_page)]
        totals.sessions += int(sessions or 0)
        totals.key_events += float(key_events or 0)
        totals.url_id = url_id or totals.url_id

    total_sessions = sum(item.sessions for item in pages.values())
    total_events = sum(item.key_events for item in pages.values())
    site_rate = total_events / total_sessions if total_sessions else 0
    url_ids = {item.url_id for item in pages.values() if item.url_id}
    urls = _url_map(db, url_ids)
    candidates = [
        (totals.sessions, landing_page, totals)
        for landing_page, totals in pages.items()
        if totals.sessions >= 100
        and (
            totals.key_events == 0
            or (site_rate >= 0.01 and totals.conversion_rate <= site_rate * 0.35)
        )
    ]

    result = []
    for _, landing_page, totals in sorted(candidates, reverse=True)[:5]:
        page_url = urls.get(totals.url_id, landing_page) if totals.url_id else landing_page
        result.append(
            {
                "type": "conversion_opportunity",
                "source": "Google Analytics 4",
                "title": "Organische landingspagina met lage conversie",
                "description": (
                    f"{totals.sessions:,} organische sessies en "
                    f"{totals.key_events:,.0f} belangrijke gebeurtenissen "
                    f"({totals.conversion_rate * 100:.1f}%)."
                ),
                "url": page_url,
                "sessions": totals.sessions,
                "key_events": round(totals.key_events, 1),
                "conversion_rate": round(totals.conversion_rate * 100, 1),
                "site_conversion_rate": round(site_rate * 100, 1),
            }
        )
    return result


def build_consultant_insights(
    db: Session,
    website_id: UUID,
    start: date,
    end: date,
    previous_start: date,
    previous_end: date,
) -> dict[str, list[dict[str, object]]]:
    search_insights = [
        {**insight, "source": "Google Search Console"}
        for insight in build_search_insights(
            db,
            website_id,
            start,
            end,
            previous_start,
            previous_end,
        )
    ]
    search_insights.extend(_page_declines(db, website_id, start, end, previous_start, previous_end))
    return {
        "search": search_insights,
        "content": build_content_intent_insights(db, website_id, start, end),
        "conversion": _conversion_opportunities(db, website_id, start, end),
    }

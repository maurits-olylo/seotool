from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.discovery import Url
from app.models.integrations import (
    GoogleAnalyticsLandingPageEventMetric,
    GoogleAnalyticsMetric,
    SearchConsoleMetric,
    WebsiteIntegration,
)
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
    previous_start: date,
    previous_end: date,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    mapping = db.scalar(
        select(WebsiteIntegration).where(
            WebsiteIntegration.website_id == website_id,
            WebsiteIntegration.service == "ga4",
        )
    )
    qualified_events = set(mapping.settings.get("qualified_key_events", [])) if mapping else set()
    data_available = bool(mapping and "last_import_landing_event_rows" in mapping.settings)
    context = {
        "configured": bool(qualified_events),
        "event_names": sorted(qualified_events),
        "data_available": data_available,
        "needs_sync": bool(qualified_events and not data_available),
    }
    if not qualified_events or not data_available:
        return [], context

    current: dict[str, LandingPagePerformance] = defaultdict(LandingPagePerformance)
    previous: dict[str, LandingPagePerformance] = defaultdict(LandingPagePerformance)
    rows = db.execute(
        select(
            GoogleAnalyticsMetric.date,
            GoogleAnalyticsMetric.landing_page,
            GoogleAnalyticsMetric.url_id,
            GoogleAnalyticsMetric.sessions,
        ).where(
            GoogleAnalyticsMetric.website_id == website_id,
            GoogleAnalyticsMetric.date >= previous_start,
            GoogleAnalyticsMetric.date <= end,
        )
    )
    for metric_date, landing_page, url_id, sessions in rows:
        if not landing_page or str(landing_page) == "(not set)":
            continue
        target = current if start <= metric_date <= end else previous
        totals = target[str(landing_page)]
        totals.sessions += int(sessions or 0)
        totals.url_id = url_id or totals.url_id

    event_rows = db.execute(
        select(
            GoogleAnalyticsLandingPageEventMetric.date,
            GoogleAnalyticsLandingPageEventMetric.landing_page,
            GoogleAnalyticsLandingPageEventMetric.url_id,
            GoogleAnalyticsLandingPageEventMetric.key_events,
        ).where(
            GoogleAnalyticsLandingPageEventMetric.website_id == website_id,
            GoogleAnalyticsLandingPageEventMetric.date >= previous_start,
            GoogleAnalyticsLandingPageEventMetric.date <= end,
            GoogleAnalyticsLandingPageEventMetric.event_name.in_(qualified_events),
        )
    )
    for metric_date, landing_page, url_id, key_events in event_rows:
        target = current if start <= metric_date <= end else previous
        totals = target[str(landing_page)]
        totals.key_events += float(key_events or 0)
        totals.url_id = url_id or totals.url_id

    total_sessions = sum(item.sessions for item in current.values())
    total_events = sum(item.key_events for item in current.values())
    site_rate = total_events / total_sessions if total_sessions else 0
    url_ids = {item.url_id for item in [*current.values(), *previous.values()] if item.url_id}
    urls = _url_map(db, url_ids)
    candidates: list[tuple[float, str, str, LandingPagePerformance, LandingPagePerformance]] = []
    for landing_page, totals in current.items():
        old = previous[landing_page]
        expected_leads = totals.sessions * site_rate
        declining = (
            old.sessions >= 100
            and old.key_events >= 5
            and totals.sessions >= old.sessions * 0.7
            and totals.conversion_rate <= old.conversion_rate * 0.6
        )
        if declining:
            candidates.append(
                (
                    old.key_events - totals.key_events + totals.sessions,
                    "decline",
                    landing_page,
                    totals,
                    old,
                )
            )
        elif totals.sessions >= 150 and totals.key_events == 0:
            candidates.append((totals.sessions, "no_leads", landing_page, totals, old))
        elif (
            totals.sessions >= 150
            and site_rate >= 0.005
            and expected_leads >= 3
            and totals.conversion_rate <= site_rate * 0.4
        ):
            candidates.append(
                (expected_leads - totals.key_events, "low_rate", landing_page, totals, old)
            )

    result: list[dict[str, object]] = []
    for _, signal, landing_page, totals, old in sorted(candidates, reverse=True)[:5]:
        page_url = urls.get(totals.url_id, landing_page) if totals.url_id else landing_page
        if signal == "decline":
            title = "Gekwalificeerde leadratio is sterk gedaald"
            description = (
                f"Van {old.key_events:,.0f} leads uit {old.sessions:,} sessies "
                f"({old.conversion_rate * 100:.1f}%) naar {totals.key_events:,.0f} uit "
                f"{totals.sessions:,} sessies ({totals.conversion_rate * 100:.1f}%)."
            )
            insight_type = "declining_conversion"
        elif signal == "no_leads":
            title = "Veel organisch verkeer zonder gekwalificeerde leads"
            description = (
                f"{totals.sessions:,} organische sessies en geen gekwalificeerde leads "
                f"uit: {', '.join(sorted(qualified_events))}."
            )
            insight_type = "traffic_without_leads"
        else:
            title = "Leadratio blijft duidelijk achter bij de website"
            description = (
                f"{totals.sessions:,} sessies en {totals.key_events:,.0f} leads "
                f"({totals.conversion_rate * 100:.1f}%) tegenover "
                f"{site_rate * 100:.1f}% voor de website."
            )
            insight_type = "low_conversion_rate"
        result.append(
            {
                "type": insight_type,
                "source": "Google Analytics 4",
                "title": title,
                "description": description,
                "url": page_url,
                "sessions": totals.sessions,
                "key_events": round(totals.key_events, 1),
                "conversion_rate": round(totals.conversion_rate * 100, 1),
                "site_conversion_rate": round(site_rate * 100, 1),
                "previous_sessions": old.sessions,
                "previous_key_events": round(old.key_events, 1),
                "previous_conversion_rate": round(old.conversion_rate * 100, 1),
                "qualified_event_names": sorted(qualified_events),
                "recommended_action": (
                    "Controleer zoekintentie, CTA, formulierwerking en eventuele wijzigingen "
                    "in de landingspagina of conversiemeting."
                ),
            }
        )
    return result, context


def build_consultant_insights(
    db: Session,
    website_id: UUID,
    start: date,
    end: date,
    previous_start: date,
    previous_end: date,
) -> dict[str, object]:
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
    conversion, conversion_context = _conversion_opportunities(
        db,
        website_id,
        start,
        end,
        previous_start,
        previous_end,
    )
    return {
        "search": search_insights,
        "content": build_content_intent_insights(db, website_id, start, end),
        "conversion": conversion,
        "conversion_context": conversion_context,
    }

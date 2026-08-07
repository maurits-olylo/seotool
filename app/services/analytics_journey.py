from collections import defaultdict
from datetime import date
from math import comb
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.content_analysis import UrlContentClassification, UrlContentOverride
from app.models.discovery import Url
from app.models.integrations import (
    GoogleAnalyticsLandingPageEventMetric,
    GoogleAnalyticsMetric,
    MatomoPageMetric,
    WebsiteIntegration,
)
from app.services.analytics_provider import primary_analytics_source

MIN_PAGE_ENTRIES = 25
MIN_PEER_PAGES = 5
MIN_PEER_ENTRIES = 200
MIN_EFFECT = 0.10
MAX_FALSE_DISCOVERY_RATE = 0.10
TERMINAL_CONTENT_ROLES = {"navigate"}


def _binomial_lower_tail(successes: int, trials: int, probability: float) -> float:
    return sum(
        comb(trials, value)
        * probability**value
        * (1 - probability) ** (trials - value)
        for value in range(successes + 1)
    )


def detect_dead_end_opportunities(
    pages: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return low-noise landing dead ends using a one-sided exact binomial test.

    The false-discovery-rate correction prevents a large website from producing signals merely
    because many pages are tested at once. True page-to-page transitions remain a separate source.
    """
    candidates: list[dict[str, object]] = []
    for page in pages:
        entries = int(page.get("entry_visits") or 0)
        bounces = min(entries, int(page.get("bounces") or 0))
        role = str(page.get("content_role") or "uncertain")
        if (
            entries < MIN_PAGE_ENTRIES
            or float(page.get("conversions") or 0) > 0
            or role in TERMINAL_CONTENT_ROLES
            or role == "uncertain"
        ):
            continue
        peers = [
            item
            for item in pages
            if item is not page
            and item.get("content_role") == role
            and int(item.get("entry_visits") or 0) > 0
        ]
        peer_entries = sum(int(item.get("entry_visits") or 0) for item in peers)
        peer_continuations = sum(
            max(0, int(item.get("entry_visits") or 0) - int(item.get("bounces") or 0))
            for item in peers
        )
        if len(peers) < MIN_PEER_PAGES or peer_entries < MIN_PEER_ENTRIES:
            continue
        benchmark = peer_continuations / peer_entries
        continuation = (entries - bounces) / entries
        null_rate = max(0.0, benchmark - MIN_EFFECT)
        if null_rate <= 0 or continuation > null_rate:
            continue
        p_value = _binomial_lower_tail(entries - bounces, entries, null_rate)
        candidates.append(
            {
                "key": f"landing-dead-end:{page['url_id']}",
                "url_id": page["url_id"],
                "url": page["url"],
                "content_role": role,
                "entry_visits": entries,
                "continuations": entries - bounces,
                "continuation_rate": round(continuation, 4),
                "benchmark_rate": round(benchmark, 4),
                "minimum_effect": MIN_EFFECT,
                "p_value": p_value,
                "peer_pages": len(peers),
                "peer_entries": peer_entries,
            }
        )

    ordered = sorted(candidates, key=lambda item: float(item["p_value"]))
    total = len(ordered)
    accepted = 0
    for rank, item in enumerate(ordered, start=1):
        if float(item["p_value"]) <= (rank / total) * MAX_FALSE_DISCOVERY_RATE:
            accepted = rank
    results = ordered[:accepted]
    for item in results:
        item["confidence"] = round(1 - float(item.pop("p_value")), 4)
        item["statistical_method"] = "exact_binomial_bh_fdr_10pct"
        item["recommendation"] = (
            "Controleer eerst of dit een bedoeld eindpunt is. Zo niet, verbeter de relevante "
            "vervolgstap met interne links of een duidelijke CTA."
        )
    return results


def _latest_classifications(db: Session, website_id: UUID) -> dict[UUID, UrlContentClassification]:
    result: dict[UUID, UrlContentClassification] = {}
    for item in db.scalars(
        select(UrlContentClassification)
        .where(UrlContentClassification.website_id == website_id)
        .order_by(UrlContentClassification.created_at.desc())
    ):
        result.setdefault(item.url_id, item)
    return result


def _coverage(db: Session, website_id: UUID, source: str) -> dict[str, object]:
    mapping = db.scalar(
        select(WebsiteIntegration).where(
            WebsiteIntegration.website_id == website_id,
            WebsiteIntegration.service == source,
        )
    )
    stored = mapping.settings.get("coverage", {}) if mapping else {}
    if source == "ga4":
        return {
            "landing_pages": "available",
            "conversions": "available",
            "micro_conversions": "unknown",
            "transitions": "unknown",
            "landing_continuation": "unknown",
        }
    return {
        "landing_pages": "available",
        "conversions": stored.get("goals", "unknown"),
        "micro_conversions": "unknown",
        "transitions": stored.get("transitions", "unknown"),
        "landing_continuation": stored.get("landing_continuation", "unknown"),
    }


def build_analytics_journey(
    db: Session, website_id: UUID, period_start: date, period_end: date
) -> dict[str, object]:
    source = primary_analytics_source(db, website_id)
    base = {
        "website_id": str(website_id),
        "period_start": period_start,
        "period_end": period_end,
        "primary_source": source,
        "interpretation": (
            "Geobserveerde samenhang binnen de gekozen analyticsbron; geen causale attributie."
        ),
    }
    if source not in {"ga4", "matomo"}:
        return {
            **base,
            "coverage": {
                "landing_pages": "unknown",
                "conversions": "unknown",
                "micro_conversions": "unknown",
                "transitions": "unknown",
                "landing_continuation": "unknown",
            },
            "pages": [],
            "stage_totals": {},
            "observed_routes": [],
            "dead_end_opportunities": [],
            "dropoff": {"status": "unknown", "reason": "Geen primaire analyticsbron gekozen."},
        }

    if source == "ga4":
        metric_rows = db.execute(
            select(
                GoogleAnalyticsMetric.url_id,
                func.sum(GoogleAnalyticsMetric.sessions),
                func.sum(GoogleAnalyticsMetric.active_users),
                func.sum(GoogleAnalyticsMetric.key_events),
                0,
                0,
                0,
            )
            .where(
                GoogleAnalyticsMetric.website_id == website_id,
                GoogleAnalyticsMetric.date >= period_start,
                GoogleAnalyticsMetric.date <= period_end,
                GoogleAnalyticsMetric.url_id.is_not(None),
            )
            .group_by(GoogleAnalyticsMetric.url_id)
        )
        event_rows = db.execute(
            select(
                GoogleAnalyticsLandingPageEventMetric.url_id,
                GoogleAnalyticsLandingPageEventMetric.event_name,
                func.sum(GoogleAnalyticsLandingPageEventMetric.key_events),
            )
            .where(
                GoogleAnalyticsLandingPageEventMetric.website_id == website_id,
                GoogleAnalyticsLandingPageEventMetric.date >= period_start,
                GoogleAnalyticsLandingPageEventMetric.date <= period_end,
                GoogleAnalyticsLandingPageEventMetric.url_id.is_not(None),
            )
            .group_by(
                GoogleAnalyticsLandingPageEventMetric.url_id,
                GoogleAnalyticsLandingPageEventMetric.event_name,
            )
        )
    else:
        metric_rows = db.execute(
            select(
                MatomoPageMetric.url_id,
                func.sum(MatomoPageMetric.visits),
                func.sum(MatomoPageMetric.unique_pageviews),
                func.sum(MatomoPageMetric.conversions),
                func.sum(MatomoPageMetric.entry_visits),
                func.sum(MatomoPageMetric.bounces),
                func.sum(MatomoPageMetric.exits),
            )
            .where(
                MatomoPageMetric.website_id == website_id,
                MatomoPageMetric.date >= period_start,
                MatomoPageMetric.date <= period_end,
                MatomoPageMetric.url_id.is_not(None),
            )
            .group_by(MatomoPageMetric.url_id)
        )
        event_rows = []

    events: dict[UUID, list[dict[str, object]]] = defaultdict(list)
    for url_id, event_name, count in event_rows:
        events[url_id].append({"name": str(event_name), "count": float(count or 0)})
    classifications = _latest_classifications(db, website_id)
    overrides = {
        item.url_id: item
        for item in db.scalars(
            select(UrlContentOverride).where(UrlContentOverride.website_id == website_id)
        )
    }
    urls = {item.id: item for item in db.scalars(select(Url).where(Url.website_id == website_id))}
    pages: list[dict[str, object]] = []
    stage_totals: dict[str, dict[str, float]] = defaultdict(
        lambda: {"visits": 0, "users": 0, "conversions": 0}
    )
    for url_id, visits, users, conversions, entry_visits, bounces, exits in metric_rows:
        url = urls.get(url_id)
        classification = classifications.get(url_id)
        if not url or not classification:
            continue
        override = overrides.get(url_id)
        stage = (
            override.journey_stage
            if override and override.is_locked and override.journey_stage
            else classification.journey_stage
        )
        role = (
            override.content_role
            if override and override.is_locked and override.content_role
            else classification.content_role
        )
        visit_count = int(visits or 0)
        user_count = int(users or 0)
        conversion_count = float(conversions or 0)
        stage_totals[stage]["visits"] += visit_count
        stage_totals[stage]["users"] += user_count
        stage_totals[stage]["conversions"] += conversion_count
        pages.append(
            {
                "url_id": str(url_id),
                "url": url.normalized_url,
                "journey_stage": stage,
                "content_role": role,
                "visits": visit_count,
                "users": user_count,
                "conversions": conversion_count,
                "conversion_rate": round(conversion_count / visit_count, 4)
                if visit_count
                else None,
                "conversion_events": events.get(url_id, []),
                "entry_visits": int(entry_visits or 0) if source == "matomo" else None,
                "bounces": int(bounces or 0) if source == "matomo" else None,
                "exits": int(exits or 0) if source == "matomo" else None,
            }
        )
    coverage = _coverage(db, website_id, source)
    transitions_available = coverage["transitions"] == "available"
    return {
        **base,
        "coverage": coverage,
        "pages": sorted(pages, key=lambda item: item["visits"], reverse=True),
        "stage_totals": dict(sorted(stage_totals.items())),
        "observed_routes": [],
        "dead_end_opportunities": (
            detect_dead_end_opportunities(pages) if source == "matomo" else []
        ),
        "dropoff": {
            "status": "not_calculated" if transitions_available else "unknown",
            "reason": (
                "Transitiedata is beschikbaar maar routeberekening volgt na bronvalidatie."
                if transitions_available
                else "De gekozen bron levert geen betrouwbare paginatransities."
            ),
        },
    }

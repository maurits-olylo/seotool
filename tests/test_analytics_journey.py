from datetime import date

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.content_analysis import UrlContentClassification, UrlContentOverride
from app.models.discovery import Url
from app.models.integrations import (
    GoogleAnalyticsLandingPageEventMetric,
    GoogleAnalyticsMetric,
    MatomoPageMetric,
)
from app.models.website import Website, WebsiteSettings
from app.services.analytics_journey import (
    build_analytics_journey,
    detect_dead_end_opportunities,
)
from app.services.content_analysis import CLASSIFICATION_VERSION


def test_journey_uses_only_selected_primary_source_and_exposes_unknown_routes() -> None:
    with SessionLocal() as db:
        client = Client(name="Journey customer")
        website = Website(client=client, name="Journey site", base_url="https://example.com")
        website.settings = WebsiteSettings(primary_analytics_source="ga4")
        db.add(website)
        db.flush()
        url = Url(website_id=website.id, normalized_url="https://example.com/offerte")
        db.add(url)
        db.flush()
        db.add_all(
            [
                UrlContentClassification(
                    website_id=website.id,
                    url_id=url.id,
                    period_start=date(2026, 8, 1),
                    period_end=date(2026, 8, 7),
                    input_hash="a" * 64,
                    classification_version=CLASSIFICATION_VERSION,
                    search_intent="transactional",
                    journey_stage="act",
                    content_role="convert",
                    confidence=0.9,
                    probabilities={"transactional": 1.0},
                    source_coverage={"crawl": True, "gsc_queries": True},
                    evidence=[],
                ),
                UrlContentOverride(
                    website_id=website.id,
                    url_id=url.id,
                    journey_stage="decide",
                    content_role="support_choice",
                    is_locked=True,
                ),
                GoogleAnalyticsMetric(
                    website_id=website.id,
                    url_id=url.id,
                    date=date(2026, 8, 3),
                    landing_page="/offerte",
                    sessions=100,
                    active_users=80,
                    key_events=10,
                ),
                GoogleAnalyticsLandingPageEventMetric(
                    website_id=website.id,
                    url_id=url.id,
                    date=date(2026, 8, 3),
                    landing_page="/offerte",
                    event_name="generate_lead",
                    key_events=10,
                ),
                MatomoPageMetric(
                    website_id=website.id,
                    url_id=url.id,
                    date=date(2026, 8, 3),
                    page_url="https://example.com/offerte",
                    visits=900,
                    pageviews=950,
                    unique_pageviews=850,
                    conversions=90,
                ),
            ]
        )
        db.commit()

        ga4 = build_analytics_journey(db, website.id, date(2026, 8, 1), date(2026, 8, 7))
        assert ga4["primary_source"] == "ga4"
        assert ga4["pages"][0]["visits"] == 100
        assert ga4["pages"][0]["conversion_events"] == [{"name": "generate_lead", "count": 10.0}]
        assert ga4["pages"][0]["journey_stage"] == "decide"
        assert ga4["stage_totals"]["decide"]["conversions"] == 10
        assert ga4["observed_routes"] == []
        assert ga4["dropoff"]["status"] == "unknown"
        assert "geen causale attributie" in ga4["interpretation"]

        website.settings.primary_analytics_source = "matomo"
        db.commit()
        matomo = build_analytics_journey(db, website.id, date(2026, 8, 1), date(2026, 8, 7))
        assert matomo["primary_source"] == "matomo"
        assert matomo["pages"][0]["visits"] == 900
        assert matomo["pages"][0]["conversion_events"] == []


def test_journey_without_primary_source_is_explicitly_unknown() -> None:
    with SessionLocal() as db:
        client = Client(name="No analytics customer")
        website = Website(client=client, name="No analytics", base_url="https://none.example.com")
        website.settings = WebsiteSettings(primary_analytics_source=None)
        db.add(website)
        db.commit()
        result = build_analytics_journey(db, website.id, date(2026, 8, 1), date(2026, 8, 7))
        assert result["primary_source"] is None
        assert result["pages"] == []
        assert result["coverage"]["transitions"] == "unknown"
        assert result["dropoff"]["status"] == "unknown"


def test_dead_end_signal_requires_effect_size_confidence_and_peer_coverage() -> None:
    peers = [
        {
            "url_id": f"peer-{index}",
            "url": f"https://example.com/peer-{index}",
            "content_role": "attract",
            "entry_visits": 40,
            "bounces": 32,
            "conversions": 0,
        }
        for index in range(5)
    ]
    candidate = {
        "url_id": "candidate",
        "url": "https://example.com/dead-end",
        "content_role": "attract",
        "entry_visits": 25,
        "bounces": 25,
        "conversions": 0,
    }

    result = detect_dead_end_opportunities([candidate, *peers])

    assert len(result) == 1
    assert result[0]["url_id"] == "candidate"
    assert result[0]["continuation_rate"] == 0
    assert result[0]["benchmark_rate"] == 0.2
    assert result[0]["confidence"] >= 0.9
    assert result[0]["statistical_method"] == "exact_binomial_bh_fdr_10pct"


def test_dead_end_signal_rejects_small_samples_conversions_and_terminal_pages() -> None:
    peers = [
        {
            "url_id": f"peer-{index}",
            "url": f"https://example.com/peer-{index}",
            "content_role": "attract",
            "entry_visits": 40,
            "bounces": 32,
            "conversions": 0,
        }
        for index in range(5)
    ]
    invalid = [
        {
            "url_id": "small",
            "url": "https://example.com/small",
            "content_role": "attract",
            "entry_visits": 24,
            "bounces": 24,
            "conversions": 0,
        },
        {
            "url_id": "converted",
            "url": "https://example.com/converted",
            "content_role": "attract",
            "entry_visits": 25,
            "bounces": 25,
            "conversions": 1,
        },
        {
            "url_id": "contact",
            "url": "https://example.com/contact",
            "content_role": "navigate",
            "entry_visits": 25,
            "bounces": 25,
            "conversions": 0,
        },
    ]

    assert detect_dead_end_opportunities([*invalid, *peers]) == []

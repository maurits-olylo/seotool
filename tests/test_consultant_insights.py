from datetime import date

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.discovery import Url
from app.models.integrations import (
    GoogleAnalyticsLandingPageEventMetric,
    GoogleAnalyticsMetric,
    IntegrationConnection,
    SearchConsoleMetric,
    WebsiteIntegration,
)
from app.models.website import Website
from app.services.consultant_insights import build_consultant_insights


def _configure_ga4(db, customer, website):  # type: ignore[no-untyped-def]
    connection = IntegrationConnection(
        client_id=customer.id,
        provider="google",
        status="connected",
    )
    db.add(connection)
    db.flush()
    mapping = WebsiteIntegration(
        website_id=website.id,
        connection_id=connection.id,
        service="ga4",
        external_property_id="properties/123",
        status="active",
        settings={
            "qualified_key_events": ["offer_request"],
            "last_import_landing_event_rows": 0,
        },
    )
    db.add(mapping)
    return mapping


def test_consultant_insights_find_page_decline_and_conversion_gap() -> None:
    with SessionLocal() as db:
        customer = Client(name="Consultant insights")
        db.add(customer)
        db.flush()
        website = Website(
            client_id=customer.id,
            name="Example",
            base_url="https://example.com",
        )
        db.add(website)
        db.flush()
        _configure_ga4(db, customer, website)
        page = Url(
            website_id=website.id,
            normalized_url="https://example.com/landing",
        )
        db.add(page)
        db.flush()
        db.add_all(
            [
                SearchConsoleMetric(
                    website_id=website.id,
                    url_id=page.id,
                    date=date(2026, 1, 10),
                    page_url=page.normalized_url,
                    clicks=50,
                    impressions=1_000,
                    ctr=0.05,
                    position=5,
                ),
                SearchConsoleMetric(
                    website_id=website.id,
                    url_id=page.id,
                    date=date(2026, 2, 10),
                    page_url=page.normalized_url,
                    clicks=10,
                    impressions=400,
                    ctr=0.025,
                    position=8,
                ),
                GoogleAnalyticsMetric(
                    website_id=website.id,
                    url_id=page.id,
                    date=date(2026, 2, 10),
                    landing_page="/landing",
                    sessions=250,
                    active_users=220,
                    key_events=0,
                ),
            ]
        )
        db.commit()

        insights = build_consultant_insights(
            db,
            website.id,
            date(2026, 2, 1),
            date(2026, 2, 28),
            date(2026, 1, 1),
            date(2026, 1, 31),
        )

    assert insights["search"][0]["type"] == "declining_page"
    assert insights["search"][0]["click_change_percent"] == -80.0
    assert insights["content"] == []
    assert insights["conversion"][0]["type"] == "traffic_without_leads"
    assert insights["conversion"][0]["url"] == "https://example.com/landing"
    assert insights["conversion_context"]["configured"] is True


def test_consultant_insights_find_declining_qualified_lead_rate() -> None:
    with SessionLocal() as db:
        customer = Client(name="Declining leads")
        website = Website(
            client=customer,
            name="Example",
            base_url="https://example.com",
        )
        db.add(website)
        db.flush()
        _configure_ga4(db, customer, website)
        page = Url(
            website_id=website.id,
            normalized_url="https://example.com/offerte",
        )
        db.add(page)
        db.flush()
        db.add_all(
            [
                GoogleAnalyticsMetric(
                    website_id=website.id,
                    url_id=page.id,
                    date=date(2026, 1, 10),
                    landing_page="/offerte",
                    sessions=200,
                    active_users=180,
                ),
                GoogleAnalyticsMetric(
                    website_id=website.id,
                    url_id=page.id,
                    date=date(2026, 2, 10),
                    landing_page="/offerte",
                    sessions=180,
                    active_users=165,
                ),
                GoogleAnalyticsLandingPageEventMetric(
                    website_id=website.id,
                    url_id=page.id,
                    date=date(2026, 1, 10),
                    landing_page="/offerte",
                    event_name="offer_request",
                    key_events=20,
                ),
                GoogleAnalyticsLandingPageEventMetric(
                    website_id=website.id,
                    url_id=page.id,
                    date=date(2026, 2, 10),
                    landing_page="/offerte",
                    event_name="offer_request",
                    key_events=5,
                ),
            ]
        )
        db.commit()

        insights = build_consultant_insights(
            db,
            website.id,
            date(2026, 2, 1),
            date(2026, 2, 28),
            date(2026, 1, 1),
            date(2026, 1, 31),
        )

    assert insights["conversion"][0]["type"] == "declining_conversion"
    assert insights["conversion"][0]["previous_conversion_rate"] == 10.0
    assert insights["conversion"][0]["conversion_rate"] == 2.8


def test_consultant_insights_compare_landing_page_with_site_lead_rate() -> None:
    with SessionLocal() as db:
        customer = Client(name="Low lead rate")
        website = Website(
            client=customer,
            name="Example",
            base_url="https://example.com",
        )
        db.add(website)
        db.flush()
        _configure_ga4(db, customer, website)
        strong = Url(website_id=website.id, normalized_url="https://example.com/strong")
        weak = Url(website_id=website.id, normalized_url="https://example.com/weak")
        db.add_all([strong, weak])
        db.flush()
        db.add_all(
            [
                GoogleAnalyticsMetric(
                    website_id=website.id,
                    url_id=strong.id,
                    date=date(2026, 2, 10),
                    landing_page="/strong",
                    sessions=500,
                    active_users=450,
                ),
                GoogleAnalyticsMetric(
                    website_id=website.id,
                    url_id=weak.id,
                    date=date(2026, 2, 10),
                    landing_page="/weak",
                    sessions=200,
                    active_users=180,
                ),
                GoogleAnalyticsLandingPageEventMetric(
                    website_id=website.id,
                    url_id=strong.id,
                    date=date(2026, 2, 10),
                    landing_page="/strong",
                    event_name="offer_request",
                    key_events=25,
                ),
                GoogleAnalyticsLandingPageEventMetric(
                    website_id=website.id,
                    url_id=weak.id,
                    date=date(2026, 2, 10),
                    landing_page="/weak",
                    event_name="offer_request",
                    key_events=1,
                ),
            ]
        )
        db.commit()

        insights = build_consultant_insights(
            db,
            website.id,
            date(2026, 2, 1),
            date(2026, 2, 28),
            date(2026, 1, 1),
            date(2026, 1, 31),
        )

    weak_insight = next(item for item in insights["conversion"] if item["url"].endswith("/weak"))
    assert weak_insight["type"] == "low_conversion_rate"
    assert weak_insight["conversion_rate"] == 0.5


def test_consultant_insights_endpoint(client) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Insights API"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Insights site",
            "base_url": "https://insights.example.com",
        },
    ).json()

    response = client.get(f"/api/v1/websites/{website['id']}/consultant-insights?days=28")

    assert response.status_code == 200
    assert response.json()["days"] == 28
    assert response.json()["search"] == []
    assert response.json()["content"] == []
    assert response.json()["conversion"] == []
    assert response.json()["conversion_context"]["configured"] is False

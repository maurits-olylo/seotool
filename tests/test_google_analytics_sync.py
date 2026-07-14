import asyncio

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.discovery import Url
from app.models.integrations import (
    GoogleAnalyticsLandingPageEventMetric,
    IntegrationConnection,
    WebsiteIntegration,
)
from app.models.website import Website
from app.services import google_analytics


def _row(dimensions: list[str], metrics: list[str]) -> dict[str, object]:
    return {
        "dimensionValues": [{"value": value} for value in dimensions],
        "metricValues": [{"value": value} for value in metrics],
    }


def test_ga4_sync_stores_key_events_per_landing_page(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def fake_token(*args, **kwargs):  # type: ignore[no-untyped-def]
        return "token"

    async def fake_report(
        http,
        endpoint,
        token,
        start_date,
        end_date,
        dimensions,
        metrics,  # type: ignore[no-untyped-def]
    ):
        if dimensions == ["date", "landingPagePlusQueryString"]:
            return [_row(["20260615", "/offerte"], ["200", "180"])]
        if dimensions == ["date", "eventName"]:
            return [_row(["20260615", "offer_request"], ["12"])]
        if dimensions == ["date", "landingPagePlusQueryString", "eventName"]:
            return [_row(["20260615", "/offerte", "offer_request"], ["12"])]
        raise AssertionError(f"Unexpected GA4 dimensions: {dimensions}")

    monkeypatch.setattr(google_analytics, "get_google_access_token", fake_token)
    monkeypatch.setattr(google_analytics, "_run_ga_report", fake_report)

    with SessionLocal() as db:
        client = Client(name="GA4 sync")
        website = Website(
            client=client,
            name="Example",
            base_url="https://example.com/",
        )
        db.add(website)
        db.flush()
        url = Url(
            website_id=website.id,
            normalized_url="https://example.com/offerte",
        )
        db.add(url)
        connection = IntegrationConnection(
            client_id=client.id,
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
            settings={"qualified_key_events": ["offer_request"]},
        )
        db.add(mapping)
        db.commit()

        result = asyncio.run(google_analytics.sync_google_analytics(db, website.id, days=28))
        metric = db.scalar(select(GoogleAnalyticsLandingPageEventMetric))

        assert result["landing_event_rows"] == 1
        assert result["landing_event_matched_urls"] == 1
        assert metric is not None
        assert metric.url_id == url.id
        assert metric.event_name == "offer_request"
        assert metric.key_events == 12
        assert mapping.settings["last_import_landing_event_rows"] == 1

from datetime import date

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.integrations import (
    GoogleAnalyticsMetric,
    IntegrationConnection,
    SearchConsoleMetric,
    SearchConsoleQueryMetric,
    WebsiteIntegration,
)
from app.models.website import Website
from app.services.integration_sync import _set_history_sync_status


def test_completed_history_sync_serializes_date_coverage() -> None:
    with SessionLocal() as db:
        customer = Client(name="History sync customer")
        db.add(customer)
        db.flush()
        website = Website(client_id=customer.id, name="Example", base_url="https://example.com")
        connection = IntegrationConnection(client_id=customer.id, provider="google", status="connected")
        db.add_all([website, connection])
        db.flush()
        db.add_all(
            [
                WebsiteIntegration(
                    website_id=website.id,
                    connection_id=connection.id,
                    service="search_console",
                    external_property_id="sc-domain:example.com",
                ),
                WebsiteIntegration(
                    website_id=website.id,
                    connection_id=connection.id,
                    service="ga4",
                    external_property_id="properties/1",
                ),
                SearchConsoleMetric(
                    website_id=website.id,
                    date=date(2026, 1, 2),
                    page_url="https://example.com/",
                ),
                SearchConsoleQueryMetric(
                    website_id=website.id,
                    date=date(2026, 1, 3),
                    query="example",
                    page_url="https://example.com/",
                ),
                GoogleAnalyticsMetric(
                    website_id=website.id,
                    date=date(2026, 1, 4),
                    landing_page="/",
                ),
            ]
        )
        db.commit()

        _set_history_sync_status(db, website.id, "succeeded", days=480)

        mappings = list(db.query(WebsiteIntegration).order_by(WebsiteIntegration.service))
        coverage = mappings[0].settings["history_sync"]["coverage"]
        assert coverage == {
            "gsc_from": "2026-01-02",
            "gsc_query_from": "2026-01-03",
            "ga4_from": "2026-01-04",
        }
        assert all(mapping.settings["history_sync"]["status"] == "succeeded" for mapping in mappings)

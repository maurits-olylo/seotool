import asyncio
from datetime import date, timedelta

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.discovery import Url
from app.models.integrations import (
    IntegrationConnection,
    SearchConsoleMetric,
    SearchConsoleQueryMetric,
    WebsiteIntegration,
)
from app.models.website import Website
from app.services.search_console import sync_search_console


def test_search_console_sync_maps_and_upserts_page_metrics(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200

        def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
            self.rows = rows or [
                {
                    "keys": [
                        (date.today() - timedelta(days=1)).isoformat(),
                        "https://example.com/page/",
                    ],
                    "clicks": 12,
                    "impressions": 1200,
                    "ctr": 0.01,
                    "position": 8.4,
                }
            ]

        def json(self) -> dict[str, object]:
            return {"rows": self.rows}

    class FakeGoogleClient:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *args):  # type: ignore[no-untyped-def]
            return None

        async def post(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            dimensions = kwargs["json"]["dimensions"]
            if dimensions == ["date", "query", "page"]:
                return FakeResponse(
                    [
                        {
                            "keys": [
                                (date.today() - timedelta(days=1)).isoformat(),
                                "example query",
                                "https://example.com/page/",
                            ],
                            "clicks": 9,
                            "impressions": 900,
                            "ctr": 0.01,
                            "position": 7.1,
                        }
                    ]
                )
            return FakeResponse()

    async def fake_token(*args, **kwargs):  # type: ignore[no-untyped-def]
        return "access-token"

    monkeypatch.setattr(
        "app.services.search_console.httpx.AsyncClient", lambda **kwargs: FakeGoogleClient()
    )
    monkeypatch.setattr("app.services.search_console.get_google_access_token", fake_token)

    with SessionLocal() as db:
        customer = Client(name="GSC client")
        db.add(customer)
        db.flush()
        website = Website(client_id=customer.id, name="Example", base_url="https://example.com")
        db.add(website)
        db.flush()
        url = Url(website_id=website.id, normalized_url="https://example.com/page")
        connection = IntegrationConnection(
            client_id=customer.id, provider="google", status="connected"
        )
        db.add_all([url, connection])
        db.flush()
        mapping = WebsiteIntegration(
            website_id=website.id,
            connection_id=connection.id,
            service="search_console",
            external_property_id="sc-domain:example.com",
        )
        db.add(mapping)
        db.commit()

        first = asyncio.run(sync_search_console(db, website.id))
        second = asyncio.run(sync_search_console(db, website.id))

        assert first["matched_urls"] == 1
        assert second["rows"] == 1
        assert db.scalar(select(func.count()).select_from(SearchConsoleMetric)) == 1
        assert db.scalar(select(func.count()).select_from(SearchConsoleQueryMetric)) == 1
        metric = db.scalar(select(SearchConsoleMetric))
        assert metric and metric.url_id == url.id and metric.clicks == 12
        query_metric = db.scalar(select(SearchConsoleQueryMetric))
        assert query_metric
        assert query_metric.query == "example query"
        assert query_metric.url_id == url.id
        assert mapping.last_synced_at is not None

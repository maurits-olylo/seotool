import asyncio
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.client import Client
from app.models.discovery import Url
from app.models.integrations import (
    BingInboundLink,
    BingLinkTarget,
    BingPageMetric,
    BingQueryMetric,
    IntegrationConnection,
    WebsiteIntegration,
)
from app.models.website import Website, WebsiteSettings
from app.services.bing_integrations import sync_bing_webmaster
from app.services.oauth import encrypt_token


def _bing_date(value: date) -> str:
    moment = datetime(value.year, value.month, value.day, tzinfo=UTC)
    return f"/Date({int(moment.timestamp() * 1000)}+0000)/"


def test_bing_sync_stores_page_and_query_metrics_idempotently(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "07" * 32)
    get_settings.cache_clear()
    metric_date = date.today() - timedelta(days=7)

    class FakeResponse:
        status_code = 200

        def __init__(self, data: object) -> None:
            self.data = data

        def json(self) -> dict[str, object]:
            return {"d": self.data}

    class FakeBingClient:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *args):  # type: ignore[no-untyped-def]
            return None

        async def get(self, url, *, params, headers):  # type: ignore[no-untyped-def]
            assert params["siteUrl"] == "https://example.com/"
            assert headers == {"Authorization": "Bearer bing-access"}
            common = {
                "Date": _bing_date(metric_date),
                "Clicks": 4,
                "Impressions": 100,
                "AvgClickPosition": 3.5,
                "AvgImpressionPosition": 4.5,
            }
            if url.endswith("GetPageStats"):
                return FakeResponse([{**common, "Query": "https://example.com/page"}])
            if url.endswith("GetQueryStats"):
                return FakeResponse([{**common, "Query": "voorbeeld zoekterm"}])
            if url.endswith("GetLinkCounts"):
                assert params["page"] == 0
                return FakeResponse(
                    {
                        "Links": [{"Url": "https://example.com/page", "Count": 12}],
                        "TotalPages": 1,
                    }
                )
            assert url.endswith("GetUrlLinks")
            assert params == {
                "siteUrl": "https://example.com/",
                "page": 0,
                "link": "https://example.com/page",
            }
            return FakeResponse(
                {
                    "Details": [
                        {
                            "Url": "https://referrer.example/article",
                            "AnchorText": "voorbeeld link",
                        }
                    ],
                    "TotalPages": 1,
                }
            )

    monkeypatch.setattr(
        "app.services.bing_integrations.httpx.AsyncClient",
        lambda **kwargs: FakeBingClient(),
    )
    try:
        with SessionLocal() as db:
            website_id = _mapped_website(db)
            first = asyncio.run(sync_bing_webmaster(db, website_id, days=480))
            second = asyncio.run(sync_bing_webmaster(db, website_id, days=480))

            assert first == second
            assert first["page_rows"] == 1
            assert first["query_rows"] == 1
            assert first["matched_urls"] == 1
            assert first["link_targets"] == 1
            assert first["link_details"] == 1
            assert first["link_counts_truncated"] is False
            assert first["link_details_truncated"] is False
            assert db.scalar(
                select(func.count(BingPageMetric.id)).where(
                    BingPageMetric.website_id == website_id
                )
            ) == 1
            assert db.scalar(
                select(func.count(BingQueryMetric.id)).where(
                    BingQueryMetric.website_id == website_id
                )
            ) == 1
            assert db.scalar(select(func.count(BingLinkTarget.id))) == 1
            assert db.scalar(select(func.count(BingInboundLink.id))) == 1
            page = db.scalar(select(BingPageMetric))
            query = db.scalar(select(BingQueryMetric))
            assert page is not None and page.url_id is not None
            assert page.clicks == 4 and page.impressions == 100
            assert query is not None and query.query == "voorbeeld zoekterm"
            link_target = db.scalar(select(BingLinkTarget))
            inbound_link = db.scalar(select(BingInboundLink))
            assert link_target is not None and link_target.url_id is not None
            assert link_target.inbound_link_count == 12 and link_target.is_active is True
            assert inbound_link is not None and inbound_link.is_active is True
            assert inbound_link.source_url == "https://referrer.example/article"
            assert inbound_link.anchor_text == "voorbeeld link"
    finally:
        get_settings.cache_clear()


def test_bing_sync_records_api_failure(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "08" * 32)
    get_settings.cache_clear()

    class FailedResponse:
        status_code = 503

    class FailedBingClient:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *args):  # type: ignore[no-untyped-def]
            return None

        async def get(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return FailedResponse()

    monkeypatch.setattr(
        "app.services.bing_integrations.httpx.AsyncClient",
        lambda **kwargs: FailedBingClient(),
    )
    try:
        with SessionLocal() as db:
            website_id = _mapped_website(db)
            try:
                asyncio.run(sync_bing_webmaster(db, website_id))
                raise AssertionError("Bing sync should fail")
            except ValueError as exc:
                assert str(exc) == "Bing Webmaster data could not be loaded"
            mapping = db.scalar(
                select(WebsiteIntegration).where(
                    WebsiteIntegration.website_id == website_id,
                    WebsiteIntegration.service == "bing_webmaster",
                )
            )
            assert mapping is not None and mapping.status == "error"
            assert "GetPageStats" in str(mapping.settings["last_error"])
    finally:
        get_settings.cache_clear()


def _mapped_website(db):  # type: ignore[no-untyped-def]
    client = Client(name="Bing client")
    website = Website(client=client, name="Bing site", base_url="https://example.com/")
    website.settings = WebsiteSettings()
    db.add(website)
    db.flush()
    page = Url(website_id=website.id, normalized_url="https://example.com/page")
    connection = IntegrationConnection(
        client_id=client.id,
        provider="bing",
        status="connected",
        encrypted_access_token=encrypt_token("bing-access"),
        encrypted_refresh_token=encrypt_token("bing-refresh"),
        token_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db.add_all([page, connection])
    db.flush()
    db.add(
        WebsiteIntegration(
            website_id=website.id,
            connection_id=connection.id,
            service="bing_webmaster",
            external_property_id="https://example.com/",
        )
    )
    db.commit()
    return website.id

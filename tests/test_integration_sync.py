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
from app.services import integration_sync
from app.services.integration_sync import (
    _history_chunks,
    _set_history_sync_status,
    _sync_matomo_history,
    _sync_search_console_history,
)


def test_completed_history_sync_serializes_date_coverage() -> None:
    with SessionLocal() as db:
        customer = Client(name="History sync customer")
        db.add(customer)
        db.flush()
        website = Website(client_id=customer.id, name="Example", base_url="https://example.com")
        connection = IntegrationConnection(
            client_id=customer.id,
            provider="google",
            status="connected",
        )
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
        assert all(
            mapping.settings["history_sync"]["status"] == "succeeded" for mapping in mappings
        )


def test_history_chunks_cover_period_without_overlap() -> None:
    chunks = _history_chunks(65, through=date(2026, 8, 4))

    assert chunks == [
        (date(2026, 6, 1), date(2026, 6, 28)),
        (date(2026, 6, 29), date(2026, 7, 26)),
        (date(2026, 7, 27), date(2026, 8, 4)),
    ]


def test_history_sync_uses_bounded_chronological_periods(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    search_calls: list[tuple[int | None, date | None]] = []
    matomo_calls: list[tuple[int | None, date | None]] = []

    async def fake_search(_db, _website_id, days, *, through=None):  # type: ignore[no-untyped-def]
        search_calls.append((days, through))
        return {
            "start_date": through - integration_sync.timedelta(days=days - 1),
            "end_date": through,
        }

    async def fake_matomo(_db, _website_id, days, *, through=None):  # type: ignore[no-untyped-def]
        matomo_calls.append((days, through))
        return {
            "start_date": through - integration_sync.timedelta(days=days - 1),
            "end_date": through,
        }

    monkeypatch.setattr(integration_sync, "sync_search_console", fake_search)
    monkeypatch.setattr(integration_sync, "sync_matomo", fake_matomo)
    monkeypatch.setattr(
        integration_sync,
        "_history_chunks",
        lambda _days: [
            (date(2026, 6, 1), date(2026, 6, 28)),
            (date(2026, 6, 29), date(2026, 7, 5)),
        ],
    )

    import asyncio
    from uuid import uuid4

    search_result = asyncio.run(_sync_search_console_history(None, uuid4(), 35))  # type: ignore[arg-type]
    matomo_result = asyncio.run(_sync_matomo_history(None, uuid4(), 35))  # type: ignore[arg-type]

    assert search_calls == [(28, date(2026, 6, 28)), (7, date(2026, 7, 5))]
    assert matomo_calls == search_calls
    assert search_result["chunks"] == 2
    assert matomo_result["start_date"] == date(2026, 6, 1)

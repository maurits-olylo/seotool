from datetime import date
from urllib.parse import parse_qs
from uuid import UUID

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.routes import integrations
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.client import Client
from app.models.discovery import Url
from app.models.integrations import (
    IntegrationConnection,
    MatomoAggregateMetric,
    MatomoPageMetric,
    WebsiteIntegration,
)
from app.models.website import Website, WebsiteSettings
from app.services import matomo
from app.services.analytics_provider import analytics_page_totals
from app.services.oauth import decrypt_token


def test_matomo_client_uses_post_body_and_sanitizes_sites(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(matomo, "validate_public_http_url", lambda _url: None)

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert "token_auth" not in str(request.url)
        assert b"token_auth=secret-token" in request.content
        return httpx.Response(
            200,
            json=[{"idsite": 7, "name": "Human", "main_url": "https://human.nl"}],
        )

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        matomo.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    import asyncio

    sites = asyncio.run(matomo.list_matomo_sites("https://analytics.example.com", "secret-token"))
    assert sites == [{"id": "7", "name": "Human", "main_url": "https://human.nl"}]


def test_connect_and_select_human_matomo_site(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "0a" * 32)
    get_settings.cache_clear()

    async def fake_sites(_server_url: str, token: str):  # type: ignore[no-untyped-def]
        assert token == "matomo-secret"
        return [{"id": "7", "name": "Human", "main_url": "https://human.nl"}]

    monkeypatch.setattr(
        integrations,
        "normalize_matomo_server_url",
        lambda _url: "https://analytics.example.com/index.php",
    )
    monkeypatch.setattr(integrations, "list_matomo_sites", fake_sites)
    customer = client.post("/api/v1/clients", json={"name": "Human"}).json()
    website = client.post(
        "/api/v1/websites",
        json={"client_id": customer["id"], "name": "Human", "base_url": "https://human.nl"},
    ).json()
    response = client.put(
        f"/api/v1/clients/{customer['id']}/integrations/matomo",
        json={"server_url": "https://analytics.example.com", "token_auth": "matomo-secret"},
    )
    assert response.status_code == 200
    assert response.json()["sites"][0]["id"] == "7"

    with SessionLocal() as db:
        connection = db.scalar(
            select(IntegrationConnection).where(IntegrationConnection.provider == "matomo")
        )
        assert connection is not None
        assert decrypt_token(connection.encrypted_access_token) == "matomo-secret"
        connection_id = connection.id

    mapping = client.put(
        f"/api/v1/websites/{website['id']}/integrations/matomo",
        json={
            "connection_id": str(connection_id),
            "external_property_id": "7",
            "external_property_name": "Human",
        },
    )
    assert mapping.status_code == 200
    assert mapping.json()["external_property_id"] == "7"
    primary = client.put(
        f"/api/v1/websites/{website['id']}/integrations/analytics-primary",
        json={"source": "matomo"},
    )
    assert primary.status_code == 200
    assert primary.json() == {"source": "matomo"}
    current_primary = client.get(f"/api/v1/websites/{website['id']}/integrations/analytics-primary")
    assert current_primary.status_code == 200
    assert current_primary.json() == {"source": "matomo"}
    with SessionLocal() as db:
        selected = db.scalar(
            select(WebsiteIntegration).where(
                WebsiteIntegration.website_id == UUID(website["id"]),
                WebsiteIntegration.service == "matomo",
            )
        )
        assert selected is not None
        assert selected.external_property_id == "7"
    get_settings.cache_clear()


def test_matomo_sync_stores_aggregates_and_url_coverage(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "0b" * 32)
    get_settings.cache_clear()
    monkeypatch.setattr(matomo, "validate_public_http_url", lambda _url: None)

    async def fake_report(_http, _endpoint, _token, method, *_args):  # type: ignore[no-untyped-def]
        if method == "Actions.getPageUrls":
            return {
                "2026-08-01": [
                    {
                        "label": "/programma",
                        "nb_visits": 10,
                        "nb_hits": 14,
                        "entry_nb_visits": 8,
                        "bounce_count": 3,
                        "exit_nb_visits": 4,
                    },
                    {"label": "/onbekend?genre=kunst", "nb_visits": 2, "nb_hits": 3},
                ]
            }
        if method == "Referrers.getReferrerType":
            return {"2026-08-01": [{"label": "Search Engines", "nb_visits": 8}]}
        return {"2026-08-01": [{"idgoal": "1", "name": "Nieuwsbrief", "nb_conversions": 2}]}

    monkeypatch.setattr(matomo, "_report", fake_report)
    with SessionLocal() as db:
        customer = Client(name="Human")
        website = Website(client=customer, name="Human", base_url="https://human.nl/")
        db.add(website)
        db.flush()
        db.add(Url(website_id=website.id, normalized_url="https://human.nl/programma"))
        connection = IntegrationConnection(
            client_id=customer.id,
            provider="matomo",
            status="connected",
            encrypted_access_token=integrations.encrypt_token("secret"),
            settings={"server_url": "https://analytics.example.com/index.php"},
        )
        db.add(connection)
        db.flush()
        mapping = WebsiteIntegration(
            website_id=website.id,
            connection_id=connection.id,
            service="matomo",
            external_property_id="7",
            status="active",
        )
        db.add(mapping)
        db.add(WebsiteSettings(website_id=website.id, primary_analytics_source="matomo"))
        db.commit()

        import asyncio

        result = asyncio.run(matomo.sync_matomo(db, website.id, days=5))
        pages = list(db.scalars(select(MatomoPageMetric).order_by(MatomoPageMetric.page_url)))
        aggregates = list(db.scalars(select(MatomoAggregateMetric)))

        assert result["page_rows"] == 2
        assert result["matched_urls"] == 1
        assert result["url_match_rate"] == 0.5
        assert len(pages) == 2
        matched_page = next(page for page in pages if page.url_id is not None)
        assert (matched_page.entry_visits, matched_page.bounces, matched_page.exits) == (8, 3, 4)
        assert len(aggregates) == 2
        source, totals = analytics_page_totals(db, website.id, date(2026, 7, 1))
        assert source == "matomo"
        assert [(item.visits, item.users) for item in totals] == [(10, 0)]
        assert mapping.settings["coverage"]["transitions"] == "not_imported"
        assert mapping.settings["coverage"]["landing_continuation"] == "available"
        assert mapping.settings["coverage"]["internal_search"] == "not_imported"
        assert mapping.settings["unmatched_url_variants"] == [
            "https://human.nl/onbekend?genre=kunst"
        ]
    get_settings.cache_clear()


def test_matomo_sync_merges_duplicate_report_rows(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "0d" * 32)
    get_settings.cache_clear()
    monkeypatch.setattr(matomo, "validate_public_http_url", lambda _url: None)

    async def fake_report(_http, _endpoint, _token, method, *_args):  # type: ignore[no-untyped-def]
        if method == "Actions.getPageUrls":
            return {
                "2026-08-01": [
                    {"label": "/dubbel", "nb_visits": 2, "nb_hits": 3},
                    {"label": "/dubbel", "nb_visits": 4, "nb_hits": 5},
                ]
            }
        return {
            "2026-08-01": [
                {"label": "duplicate", "nb_visits": 2},
                {"label": "duplicate", "nb_visits": 4},
            ]
        }

    monkeypatch.setattr(matomo, "_report", fake_report)
    with SessionLocal() as db:
        customer = Client(name="Duplicate Matomo rows")
        website = Website(client=customer, name="Duplicate", base_url="https://example.com/")
        db.add(website)
        db.flush()
        db.add(Url(website_id=website.id, normalized_url="https://example.com/dubbel"))
        connection = IntegrationConnection(
            client_id=customer.id,
            provider="matomo",
            status="connected",
            encrypted_access_token=integrations.encrypt_token("secret"),
            settings={"server_url": "https://analytics.example.com/index.php"},
        )
        db.add(connection)
        db.flush()
        db.add(
            WebsiteIntegration(
                website_id=website.id,
                connection_id=connection.id,
                service="matomo",
                external_property_id="7",
                status="active",
            )
        )
        db.commit()

        import asyncio

        result = asyncio.run(matomo.sync_matomo(db, website.id, days=1))
        pages = list(db.scalars(select(MatomoPageMetric)))
        aggregates = list(db.scalars(select(MatomoAggregateMetric)))

        assert result["page_rows"] == 1
        assert result["matched_urls"] == 1
        assert len(pages) == 1
        assert pages[0].visits == 6
        assert pages[0].pageviews == 8
        assert len(aggregates) == 2
        assert {row.metric_type: row.visits for row in aggregates} == {
            "goal": 6,
            "traffic_source": 6,
        }
    get_settings.cache_clear()


def test_matomo_sync_keeps_pages_when_optional_report_is_unavailable(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "0c" * 32)
    get_settings.cache_clear()
    monkeypatch.setattr(matomo, "validate_public_http_url", lambda _url: None)

    async def fake_report(_http, _endpoint, _token, method, *_args):  # type: ignore[no-untyped-def]
        if method == "Actions.getPageUrls":
            return {"2026-08-01": [{"label": "/programma", "nb_visits": 10}]}
        if method == "Goals.get":
            raise matomo.MatomoReportError(
                method, "dit rapport is niet beschikbaar in deze Matomo-installatie"
            )
        return {"2026-08-01": [{"label": "Search Engines", "nb_visits": 8}]}

    monkeypatch.setattr(matomo, "_report", fake_report)
    with SessionLocal() as db:
        customer = Client(name="Human partial")
        website = Website(client=customer, name="Human partial", base_url="https://human.nl/")
        db.add(website)
        db.flush()
        connection = IntegrationConnection(
            client_id=customer.id,
            provider="matomo",
            status="connected",
            encrypted_access_token=integrations.encrypt_token("secret"),
            settings={"server_url": "https://analytics.example.com/index.php"},
        )
        db.add(connection)
        db.flush()
        mapping = WebsiteIntegration(
            website_id=website.id,
            connection_id=connection.id,
            service="matomo",
            external_property_id="7",
            status="active",
        )
        db.add(mapping)
        db.commit()

        import asyncio

        result = asyncio.run(matomo.sync_matomo(db, website.id, days=5))

        assert result["status"] == "partially_succeeded"
        assert result["page_rows"] == 1
        assert result["coverage"]["traffic_sources"] == "available"
        assert result["coverage"]["goals"] == "unavailable"
        assert result["warnings"] == [
            "Doelen en conversies: dit rapport is niet beschikbaar in deze Matomo-installatie"
        ]
        assert mapping.status == "active"
        assert mapping.settings["last_error"] == result["warnings"][0]
    get_settings.cache_clear()


def test_matomo_report_classifies_api_error_without_exposing_raw_message(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": "error", "message": "Plugin disabled: secret"})

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        matomo.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    import asyncio

    async def request_report() -> None:
        async with matomo.httpx.AsyncClient() as http:
            await matomo._report(
                http,
                "https://analytics.example.com/index.php",
                "secret-token",
                "Goals.get",
                "7",
                date(2026, 8, 1),
                date(2026, 8, 2),
            )

    try:
        asyncio.run(request_report())
    except matomo.MatomoReportError as exc:
        assert str(exc) == (
            "Doelen en conversies: dit rapport is niet beschikbaar in deze Matomo-installatie"
        )
        assert "secret" not in str(exc)
    else:
        raise AssertionError("MatomoReportError was not raised")


def test_matomo_report_uses_method_specific_parameters(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, dict[str, list[str]]] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        parameters = parse_qs(request.content.decode())
        captured[parameters["method"][0]] = parameters
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        matomo.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    import asyncio

    async def request_reports() -> None:
        async with matomo.httpx.AsyncClient() as http:
            for method in ("Actions.getPageUrls", "Referrers.getReferrerType", "Goals.get"):
                await matomo._report(
                    http,
                    "https://analytics.example.com/index.php",
                    "secret-token",
                    method,
                    "7",
                    date(2026, 8, 1),
                    date(2026, 8, 2),
                )

    asyncio.run(request_reports())

    assert captured["Actions.getPageUrls"]["flat"] == ["1"]
    assert captured["Actions.getPageUrls"]["expanded"] == ["1"]
    assert "flat" not in captured["Referrers.getReferrerType"]
    assert "expanded" not in captured["Referrers.getReferrerType"]
    assert "flat" not in captured["Goals.get"]
    assert "expanded" not in captured["Goals.get"]

import asyncio
from types import SimpleNamespace

import httpx

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.performance import PerformanceObservation
from app.models.website import Website, WebsiteSettings
from app.services.performance_sync import sync_pagespeed_performance


def test_sync_persists_once_and_retry_skips_recent_success(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.services import performance_sync

    monkeypatch.setattr(
        performance_sync,
        "get_settings",
        lambda: SimpleNamespace(pagespeed_enabled=True, pagespeed_api_key="secret-test-key"),
    )
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        assert "secret-test-key" in str(request.url)
        return httpx.Response(
            200,
            json={
                "lighthouseResult": {
                    "finalDisplayedUrl": "https://example.com/important",
                    "lighthouseVersion": "13.0.0",
                    "categories": {"performance": {"score": 0.8}},
                    "audits": {},
                }
            },
        )

    with SessionLocal() as db:
        website = _website_with_snapshot(db)
        transport = httpx.MockTransport(handler)

        async def run_syncs():  # type: ignore[no-untyped-def]
            async with httpx.AsyncClient(transport=transport) as http:
                first = await sync_pagespeed_performance(
                    db, website_id=website.id, strategy="mobile", limit=10, http=http
                )
                retry = await sync_pagespeed_performance(
                    db, website_id=website.id, strategy="mobile", limit=10, http=http
                )
                return first, retry

        first, retry = asyncio.run(run_syncs())

        assert first["measured"] == 1
        assert retry["selected"] == 0
        assert requests == 1
        assert db.query(PerformanceObservation).count() == 1


def test_failure_storage_never_contains_api_key(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.services import performance_sync

    monkeypatch.setattr(
        performance_sync,
        "get_settings",
        lambda: SimpleNamespace(pagespeed_enabled=True, pagespeed_api_key="secret-test-key"),
    )
    with SessionLocal() as db:
        website = _website_with_snapshot(db)
        transport = httpx.MockTransport(lambda _request: httpx.Response(429, json={"error": {}}))

        async def run_sync():  # type: ignore[no-untyped-def]
            async with httpx.AsyncClient(transport=transport) as http:
                return await sync_pagespeed_performance(
                    db, website_id=website.id, strategy="mobile", limit=10, http=http
                )

        result = asyncio.run(run_sync())

        observation = db.query(PerformanceObservation).one()
        assert result["status"] == "partially_succeeded"
        assert observation.error_code == "http_429"
        assert "secret-test-key" not in (observation.error_message or "")


def test_pagespeed_api_stays_disabled_by_default(client) -> None:  # type: ignore[no-untyped-def]
    customer = client.post("/api/v1/clients", json={"name": "Performance client"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Performance site",
            "base_url": "https://performance.test/",
        },
    ).json()

    response = client.post(
        f"/api/v1/websites/{website['id']}/integrations/pagespeed/sync"
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "PageSpeed is not enabled"


def _website_with_snapshot(db):  # type: ignore[no-untyped-def]
    website = Website(
        client=Client(name="Performance sync client"),
        name="Performance sync site",
        base_url="https://example.com/",
    )
    website.settings = WebsiteSettings()
    db.add(website)
    db.flush()
    url = Url(
        website_id=website.id,
        normalized_url="https://example.com/important",
        is_active=True,
        is_important=True,
        current_status_code=200,
        is_indexable=True,
    )
    job = CrawlJob(website_id=website.id, job_type="full_site_crawl", status="succeeded")
    db.add_all([url, job])
    db.flush()
    run = CrawlRun(
        crawl_job_id=job.id,
        website_id=website.id,
        crawl_type="full_site_crawl",
        status="succeeded",
    )
    db.add(run)
    db.flush()
    db.add(
        UrlSnapshot(
            url_id=url.id,
            crawl_run_id=run.id,
            requested_url=url.normalized_url,
            final_url=url.normalized_url,
            status_code=200,
            content_type="text/html",
            redirect_chain=[],
        )
    )
    db.commit()
    return website

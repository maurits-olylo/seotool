from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.assets import Asset
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.website import Website, WebsiteSettings
from app.services.asset_registry import update_asset_record


def test_asset_register_reuses_url_identity_and_updates_current_state() -> None:
    with SessionLocal() as db:
        website, url, run = _context(db)
        first = _snapshot(url, run, status_code=200, response_size=100_000)
        db.add(first)
        db.flush()

        original = update_asset_record(db, url=url, snapshot=first)
        second = _snapshot(url, run, status_code=404, response_size=0)
        db.add(second)
        db.flush()
        updated = update_asset_record(db, url=url, snapshot=second)

        assert original is not None
        assert updated is original
        assert updated.kind == "image"
        assert updated.status_code == 404
        assert updated.response_size == 0
        assert db.scalar(select(Asset).where(Asset.url_id == url.id)) is updated


def test_html_page_is_not_added_to_asset_register() -> None:
    with SessionLocal() as db:
        website, url, run = _context(db, path="/page")
        snapshot = _snapshot(url, run, content_type="text/html")
        db.add(snapshot)
        db.flush()

        assert update_asset_record(db, url=url, snapshot=snapshot) is None


def test_asset_api_is_filtered_and_tenant_scoped(client) -> None:  # type: ignore[no-untyped-def]
    first_client = client.post("/api/v1/clients", json={"name": "Asset API client"}).json()
    first_website = client.post(
        "/api/v1/websites",
        json={
            "client_id": first_client["id"],
            "name": "Asset API site",
            "base_url": "https://example.com",
        },
    ).json()
    second_client = client.post("/api/v1/clients", json={"name": "Other client"}).json()
    second_website = client.post(
        "/api/v1/websites",
        json={
            "client_id": second_client["id"],
            "name": "Other site",
            "base_url": "https://other.example",
        },
    ).json()
    with SessionLocal() as db:
        _stored_asset(db, UUID(first_website["id"]), "https://example.com/image.webp", "image")
        _stored_asset(db, UUID(first_website["id"]), "https://example.com/file.pdf", "document")
        _stored_asset(db, UUID(second_website["id"]), "https://other.example/secret.webp", "image")
        db.commit()

    response = client.get(f"/api/v1/websites/{first_website['id']}/assets?kind=image")

    assert response.status_code == 200
    assert [item["url"] for item in response.json()] == ["https://example.com/image.webp"]


def _context(db, *, path="/image.webp"):  # type: ignore[no-untyped-def]
    client = Client(name="Asset client")
    website = Website(client=client, name="Asset site", base_url="https://example.com/")
    website.settings = WebsiteSettings()
    db.add(website)
    db.flush()
    url = Url(website_id=website.id, normalized_url=f"https://example.com{path}")
    job = CrawlJob(website_id=website.id, job_type="full_site_crawl")
    db.add_all([url, job])
    db.flush()
    run = CrawlRun(
        crawl_job_id=job.id,
        website_id=website.id,
        crawl_type="full_site_crawl",
    )
    db.add(run)
    db.flush()
    return website, url, run


def _snapshot(
    url,
    run,
    *,
    status_code=200,
    response_size=100,
    content_type="image/webp",
):  # type: ignore[no-untyped-def]
    return UrlSnapshot(
        url_id=url.id,
        crawl_run_id=run.id,
        requested_url=url.normalized_url,
        final_url=url.normalized_url,
        status_code=status_code,
        redirect_chain=[],
        content_type=content_type,
        response_size=response_size,
        is_indexable=False,
    )


def _stored_asset(db, website_id, normalized_url, kind):  # type: ignore[no-untyped-def]
    url = Url(website_id=website_id, normalized_url=normalized_url)
    db.add(url)
    db.flush()
    db.add(
        Asset(
            website_id=website_id,
            url_id=url.id,
            kind=kind,
            status_code=200,
            content_type="image/webp" if kind == "image" else "application/pdf",
        )
    )

from uuid import UUID

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.crawl import CrawlRun
from app.models.discovery import CrawlJob
from app.models.issues import Issue, IssueOccurrence


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_crud_client_and_website(client: TestClient) -> None:
    created = client.post("/api/v1/clients", json={"name": "Example"})
    assert created.status_code == 201
    client_id = created.json()["id"]

    website = client.post(
        "/api/v1/websites",
        json={"client_id": client_id, "name": "Site", "base_url": "https://example.com"},
    )
    assert website.status_code == 201
    website_id = website.json()["id"]
    settings = client.get(f"/api/v1/websites/{website_id}/settings")
    assert settings.json()["respect_robots_txt"] is True


def test_api_requires_key() -> None:
    from app.main import app

    response = TestClient(app).get("/api/v1/clients")
    assert response.status_code == 401


def test_interface_login_creates_http_only_session() -> None:
    from app.main import app

    browser = TestClient(app)
    assert browser.get("/").status_code == 200
    assert browser.post("/ui/login", json={"api_key": "wrong"}).status_code == 401

    login = browser.post("/ui/login", json={"api_key": "test-key"})
    assert login.status_code == 204
    assert "HttpOnly" in login.headers["set-cookie"]
    assert browser.get("/api/v1/clients").status_code == 200

    assert browser.post("/ui/logout").status_code == 204
    assert browser.get("/api/v1/clients").status_code == 401


def test_issue_detail_exposes_evidence_and_updates_status(client: TestClient) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Issue UI"}).json()
    website = client.post(
        "/api/v1/websites",
        json={"client_id": customer["id"], "name": "Issue site", "base_url": "https://example.com"},
    ).json()
    website_id = UUID(website["id"])
    with SessionLocal() as db:
        job = CrawlJob(website_id=website_id, job_type="full_site_crawl")
        db.add(job)
        db.flush()
        run = CrawlRun(crawl_job_id=job.id, website_id=website_id, crawl_type="full_site_crawl")
        db.add(run)
        db.flush()
        issue = Issue(
            website_id=website_id,
            issue_type="http_404",
            category="reachability",
            severity="high",
            title="Pagina geeft 404",
            description="De URL geeft een 404.",
            recommended_action="Herstel de pagina.",
        )
        db.add(issue)
        db.flush()
        db.add(
            IssueOccurrence(
                issue_id=issue.id,
                crawl_run_id=run.id,
                evidence={"status_code": 404},
            )
        )
        db.commit()
        issue_id = issue.id

    detail = client.get(f"/api/v1/issues/{issue_id}")
    assert detail.status_code == 200
    assert detail.json()["evidence"] == {"status_code": 404}
    assert detail.json()["source_urls"] == []

    updated = client.patch(f"/api/v1/issues/{issue_id}", json={"status": "planned"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "planned"


def test_client_integration_and_website_property_mapping(client: TestClient) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Integrated client"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Integrated site",
            "base_url": "https://integrated.example.com",
        },
    ).json()
    connection = client.post(
        f"/api/v1/clients/{customer['id']}/integrations",
        json={"provider": "google", "account_email": "seo@example.com"},
    )
    assert connection.status_code == 201
    assert "encrypted_refresh_token" not in connection.json()

    mapping = client.post(
        f"/api/v1/websites/{website['id']}/integrations",
        json={
            "connection_id": connection.json()["id"],
            "service": "search_console",
            "external_property_id": "sc-domain:integrated.example.com",
        },
    )
    assert mapping.status_code == 201
    assert mapping.json()["service"] == "search_console"
    assert len(client.get(f"/api/v1/clients/{customer['id']}/integrations").json()) == 1
    assert len(client.get(f"/api/v1/websites/{website['id']}/integrations").json()) == 1


def test_proxied_http_redirects_to_https_in_production(monkeypatch) -> None:
    from app.main import app

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("API_KEY", "a-long-production-secret")
    get_settings.cache_clear()
    try:
        response = TestClient(app).get(
            "/health?probe=true",
            headers={"X-Forwarded-Proto": "http", "Host": "seo.thact.nl"},
            follow_redirects=False,
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 308
    assert response.headers["location"] == "https://seo.thact.nl/health?probe=true"


def test_direct_production_healthcheck_is_not_redirected(monkeypatch) -> None:
    from app.main import app

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("API_KEY", "a-long-production-secret")
    get_settings.cache_clear()
    try:
        response = TestClient(app).get("/health")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200


def test_url_registry_deduplicates_and_creates_job(client: TestClient) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Discovery"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Discovery site",
            "base_url": "https://example.com",
        },
    ).json()
    endpoint = f"/api/v1/websites/{website['id']}/urls"
    first = client.post(endpoint, json={"url": "https://example.com/page?utm_source=x"})
    second = client.post(endpoint, json={"url": "https://EXAMPLE.com/page"})
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert len(client.get(endpoint).json()) == 1

    job = client.post(
        "/api/v1/crawl-jobs",
        json={"website_id": website["id"], "job_type": "fetch_sitemap"},
    )
    assert job.status_code == 201
    assert job.json()["status"] == "pending"

    export = client.post(
        "/api/v1/exports",
        json={"website_id": website["id"], "export_type": "excel"},
    )
    assert export.status_code == 201
    assert export.json()["status"] == "pending"
    exports = client.get(f"/api/v1/exports?website_id={website['id']}")
    assert exports.status_code == 200
    assert [item["id"] for item in exports.json()] == [export.json()["id"]]

from fastapi.testclient import TestClient

from app.core.config import get_settings


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

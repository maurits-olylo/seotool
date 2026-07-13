from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.security import create_session_token, hash_password
from app.db.session import SessionLocal
from app.models.crawl import CrawlRun
from app.models.discovery import CrawlJob
from app.models.integrations import (
    GoogleAnalyticsEventMetric,
    GoogleAnalyticsMetric,
    IntegrationConnection,
    SearchConsoleMetric,
    WebsiteIntegration,
)
from app.models.issues import Issue, IssueOccurrence
from app.models.reporting import MonthlyReportSnapshot
from app.models.user import ClientMembership, User


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
    assert browser.get("/app", follow_redirects=False).headers["location"] == "/login"
    with SessionLocal() as db:
        db.add(
            User(
                email="team@example.com",
                display_name="Team member",
                role="admin",
                password_hash=hash_password("correct-horse-battery-staple"),
            )
        )
        db.commit()
    assert (
        browser.post(
            "/ui/login",
            json={"email": "team@example.com", "password": "wrong-password"},
        ).status_code
        == 401
    )

    login = browser.post(
        "/ui/login",
        json={
            "email": "team@example.com",
            "password": "correct-horse-battery-staple",
        },
    )
    assert login.status_code == 204
    assert "HttpOnly" in login.headers["set-cookie"]
    assert browser.get("/app").status_code == 200
    assert browser.get("/api/v1/clients").status_code == 200

    assert browser.post("/ui/logout").status_code == 204
    assert browser.get("/api/v1/clients").status_code == 401


def test_login_clears_session_for_missing_user() -> None:
    from app.main import app

    browser = TestClient(app)
    browser.cookies.set("seo_session", create_session_token(UUID(int=999)))
    response = browser.get("/login", follow_redirects=False)
    assert response.status_code == 200
    assert "seo_session=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]


def test_only_one_superuser_can_exist() -> None:
    with SessionLocal() as db:
        db.add_all(
            [
                User(
                    email="first@example.com",
                    role="superuser",
                    password_hash=hash_password("first-secure-password"),
                ),
                User(
                    email="second@example.com",
                    role="superuser",
                    password_hash=hash_password("second-secure-password"),
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_user_only_sees_assigned_client_and_cannot_start_crawl(client: TestClient) -> None:
    assigned = client.post("/api/v1/clients", json={"name": "Assigned"}).json()
    hidden = client.post("/api/v1/clients", json={"name": "Hidden"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": assigned["id"],
            "name": "Assigned site",
            "base_url": "https://assigned.example.com",
        },
    ).json()
    with SessionLocal() as db:
        user = User(
            email="viewer@example.com",
            role="user",
            password_hash=hash_password("viewer-secure-password"),
        )
        db.add(user)
        db.flush()
        db.add(ClientMembership(user_id=user.id, client_id=UUID(assigned["id"]), role="user"))
        db.commit()

    from app.main import app

    browser = TestClient(app)
    assert (
        browser.post(
            "/ui/login",
            json={"email": "viewer@example.com", "password": "viewer-secure-password"},
        ).status_code
        == 204
    )
    visible = browser.get("/api/v1/clients")
    assert [item["id"] for item in visible.json()] == [assigned["id"]]
    assert hidden["id"] not in {item["id"] for item in visible.json()}
    denied = browser.post(
        "/api/v1/crawl-jobs",
        json={"website_id": website["id"], "job_type": "light_check"},
    )
    assert denied.status_code == 403


def test_client_role_is_report_only(client: TestClient) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Report customer"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Report site",
            "base_url": "https://report.example.com",
        },
    ).json()
    website_id = UUID(website["id"])
    with SessionLocal() as db:
        report_user = User(
            email="client@example.com",
            role="client",
            password_hash=hash_password("client-secure-password"),
        )
        db.add(report_user)
        db.flush()
        db.add(
            ClientMembership(
                user_id=report_user.id,
                client_id=UUID(customer["id"]),
                role="client",
            )
        )
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
        db.commit()
        issue_id = issue.id

    from app.main import app

    browser = TestClient(app)
    assert browser.post(
        "/ui/login",
        json={"email": "client@example.com", "password": "client-secure-password"},
    ).status_code == 204
    assert browser.get(f"/api/v1/websites/{website_id}/issues").status_code == 200
    assert browser.patch(
        f"/api/v1/issues/{issue_id}", json={"status": "planned"}
    ).status_code == 403
    assert browser.post(
        "/api/v1/exports",
        json={"website_id": str(website_id), "export_type": "excel"},
    ).status_code == 403


def test_admin_can_manage_other_client_members(client: TestClient) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Managed customer"}).json()
    with SessionLocal() as db:
        admin = User(
            email="admin@example.com",
            role="admin",
            password_hash=hash_password("Admin-secure-password-1!"),
        )
        member = User(
            email="managed@example.com",
            role="client",
            password_hash=hash_password("Managed-secure-password-1!"),
        )
        db.add_all([admin, member])
        db.flush()
        db.add_all(
            [
                ClientMembership(
                    user_id=admin.id,
                    client_id=UUID(customer["id"]),
                    role="admin",
                ),
                ClientMembership(
                    user_id=member.id,
                    client_id=UUID(customer["id"]),
                    role="client",
                ),
            ]
        )
        db.commit()
        admin_id = admin.id
        member_id = member.id

    from app.main import app

    browser = TestClient(app)
    assert browser.post(
        "/ui/login",
        json={"email": "admin@example.com", "password": "Admin-secure-password-1!"},
    ).status_code == 204
    upgraded = browser.patch(
        f"/api/v1/clients/{customer['id']}/members/{member_id}",
        json={"role": "user"},
    )
    assert upgraded.status_code == 200
    assert upgraded.json()["client_role"] == "user"
    assert browser.patch(
        f"/api/v1/clients/{customer['id']}/members/{admin_id}",
        json={"role": "client"},
    ).status_code == 409
    assert browser.delete(
        f"/api/v1/clients/{customer['id']}/members/{member_id}"
    ).status_code == 204
    with SessionLocal() as db:
        removed = db.get(User, member_id)
        assert removed and removed.is_active is False
    reinvited = browser.post(
        "/api/v1/invitations",
        json={"email": "managed@example.com", "client_id": customer["id"], "role": "client"},
    )
    assert reinvited.status_code == 201
    token = reinvited.json()["accept_path"].split("token=", maxsplit=1)[1]
    accepted = TestClient(app).post(
        f"/api/v1/invitations/{token}/accept",
        json={"password": "Restored-secure-password-1!"},
    )
    assert accepted.status_code == 204
    with SessionLocal() as db:
        restored = db.get(User, member_id)
        membership = db.scalar(
            select(ClientMembership).where(ClientMembership.user_id == member_id)
        )
        assert restored and restored.is_active is True
        assert membership and membership.role == "client"


def test_client_report_contains_performance_and_work(client: TestClient) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Reporting"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Reporting site",
            "base_url": "https://reporting.example.com",
        },
    ).json()
    website_id = UUID(website["id"])
    yesterday = date.today() - timedelta(days=1)
    with SessionLocal() as db:
        connection = IntegrationConnection(client_id=UUID(customer["id"]), provider="google")
        db.add(connection)
        db.flush()
        db.add(
            WebsiteIntegration(
                website_id=website_id,
                connection_id=connection.id,
                service="ga4",
                external_property_id="properties/1",
                settings={"qualified_key_events": ["offer_request"]},
            )
        )
        db.add_all(
            [
                SearchConsoleMetric(
                    website_id=website_id,
                    date=yesterday,
                    page_url="https://reporting.example.com/",
                    clicks=25,
                    impressions=500,
                    ctr=0.05,
                    position=4,
                ),
                GoogleAnalyticsMetric(
                    website_id=website_id,
                    date=yesterday,
                    landing_page="/",
                    sessions=40,
                    active_users=30,
                    key_events=3,
                ),
                GoogleAnalyticsEventMetric(
                    website_id=website_id,
                    date=yesterday,
                    event_name="offer_request",
                    key_events=3,
                ),
                SearchConsoleMetric(
                    website_id=website_id,
                    date=yesterday - timedelta(days=30),
                    page_url="https://reporting.example.com/",
                    clicks=10,
                    impressions=200,
                    ctr=0.05,
                    position=6,
                ),
                SearchConsoleMetric(
                    website_id=website_id,
                    date=yesterday - timedelta(days=59),
                    page_url="https://reporting.example.com/archive",
                    clicks=0,
                    impressions=1,
                    ctr=0,
                    position=10,
                ),
            ]
        )
        db.commit()
    report = client.get(f"/api/v1/websites/{website_id}/client-report?period=month")
    assert report.status_code == 200
    assert report.json()["current"]["clicks"] == 25
    assert report.json()["current"]["key_events"] == 3
    assert report.json()["qualified_key_events"]["events"] == [
        {"event_name": "offer_request", "key_events": 3}
    ]
    assert report.json()["comparisons"]["clicks"] == 150
    assert report.json()["monthly"]


def test_monthly_report_snapshots_are_listed_and_readable(client: TestClient) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Archive"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Archive site",
            "base_url": "https://archive.example.com",
        },
    ).json()
    website_id = UUID(website["id"])
    with SessionLocal() as db:
        snapshot = MonthlyReportSnapshot(
            website_id=website_id,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            generated_at=datetime.now(UTC),
            report_data={"period": "monthly_snapshot", "current": {"sessions": 42}},
        )
        db.add(snapshot)
        db.commit()
        snapshot_id = snapshot.id
    listed = client.get(f"/api/v1/websites/{website_id}/monthly-reports")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == str(snapshot_id)
    detail = client.get(f"/api/v1/websites/{website_id}/monthly-reports/{snapshot_id}")
    assert detail.status_code == 200
    assert detail.json()["current"]["sessions"] == 42


def test_superuser_invites_user_for_client(client: TestClient) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Invitation client"}).json()
    with SessionLocal() as db:
        db.add(
            User(
                email="owner@example.com",
                role="superuser",
                password_hash=hash_password("owner-secure-password"),
            )
        )
        db.commit()

    from app.main import app

    browser = TestClient(app)
    assert (
        browser.post(
            "/ui/login",
            json={"email": "owner@example.com", "password": "owner-secure-password"},
        ).status_code
        == 204
    )
    invitation = browser.post(
        "/api/v1/invitations",
        json={"email": "member@example.com", "client_id": customer["id"], "role": "user"},
    )
    assert invitation.status_code == 201
    token = invitation.json()["accept_path"].split("token=", maxsplit=1)[1]
    invited_browser = TestClient(app)
    preview = invited_browser.get(f"/api/v1/invitations/{token}")
    assert preview.status_code == 200
    assert preview.json()["email"] == "member@example.com"
    accepted = invited_browser.post(
        f"/api/v1/invitations/{token}/accept",
        json={"password": "Member-secure-password-1!"},
    )
    assert accepted.status_code == 204
    assert "HttpOnly" in accepted.headers["set-cookie"]
    assert invited_browser.get("/app").status_code == 200
    with SessionLocal() as db:
        member = db.scalar(select(User).where(User.email == "member@example.com"))
        assert member and member.role == "user"
        membership = db.scalar(
            select(ClientMembership).where(ClientMembership.user_id == member.id)
        )
        assert membership and str(membership.client_id) == customer["id"]


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
    duplicate_export = client.post(
        "/api/v1/exports",
        json={"website_id": website["id"], "export_type": "excel"},
    )
    assert duplicate_export.status_code == 409
    exports = client.get(f"/api/v1/exports?website_id={website['id']}")
    assert exports.status_code == 200
    assert [item["id"] for item in exports.json()] == [export.json()["id"]]

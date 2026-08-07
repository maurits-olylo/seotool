from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.routes.reports import _period_dates
from app.core.config import get_settings
from app.core.security import (
    ADMIN_SESSION_TTL_SECONDS,
    USER_SESSION_TTL_SECONDS,
    create_session_token,
    hash_password,
    session_ttl_seconds,
    verify_password,
)
from app.db.session import SessionLocal
from app.models.crawl import CrawlRun, ElementLocation, UrlLink, UrlSnapshot
from app.models.discovery import CrawlJob, Url, UrlSource
from app.models.integrations import (
    GoogleAnalyticsEventMetric,
    GoogleAnalyticsMetric,
    IntegrationConnection,
    SearchConsoleMetric,
    WebsiteIntegration,
)
from app.models.issues import ActivityLog, Issue, IssueOccurrence, IssueSuppression
from app.models.reporting import MonthlyReportSnapshot
from app.models.user import ClientMembership, SecurityAuditEvent, User
from app.models.website import WebsiteSettings
from app.services.mfa import totp_code


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_issue_bulk_controls_and_client_logic_are_served(client: TestClient) -> None:
    page = client.get("/ui/assets/index.html")
    assert page.status_code == 200
    assert 'id="select-filtered-issues"' in page.text
    assert 'id="scope-filter"' in page.text
    assert 'id="nature-filter"' in page.text
    assert 'id="resolve-selected-issues"' in page.text
    assert 'id="wont-fix-selected-issues"' in page.text
    assert 'id="wont-fix-issue"' in page.text
    assert 'id="suppress-selected-issues"' in page.text
    assert 'id="suppression-panel"' in page.text
    assert 'id="issue-detail-loading"' in page.text

    script = client.get("/ui/assets/app.js")
    assert script.status_code == 200
    assert 'runIssueBulkAction("resolve_and_recheck")' in script.text
    assert 'runIssueBulkAction("wont_fix")' in script.text
    assert 'runIssueBulkAction("suppress_issue_type")' in script.text
    assert "restoreSuppression" in script.text
    assert "restoreSelectedSuppressions" in script.text
    assert "Details worden geladen…" in script.text


def test_information_architecture_and_legacy_routes_are_served(client: TestClient) -> None:
    page = client.get("/ui/assets/index.html")
    assert page.status_code == 200
    for element_id in [
        "dashboard-nav",
        "analysis-nav",
        "reports-nav",
        "operations-nav",
        "settings-nav",
        "context-bar",
        "profile-toggle",
        "mobile-nav-toggle",
    ]:
        assert f'id="{element_id}"' in page.text
    assert '<button id="logout"' not in page.text.split("</nav>", maxsplit=1)[0]

    script = client.get("/ui/assets/app.js")
    assert script.status_code == 200
    assert 'actions: "analyse/acties"' in script.text
    assert 'reports: "rapportages"' in script.text
    assert 'operations: "crawls-exports"' in script.text
    assert 'organisatie: "clients"' in script.text
    assert 'rapportage: "reports"' in script.text


def test_analysis_pages_share_consistent_states_and_labels(client: TestClient) -> None:
    page = client.get("/ui/assets/index.html")
    assert page.status_code == 200
    assert 'href="/ui/assets/analysis-consistency.css' in page.text
    assert page.text.count('<span class="eyebrow">ANALYSE</span><h1>') == 5
    assert 'class="issue-table"' in page.text
    for element_id in ["url-empty", "change-empty", "vacancy-empty"]:
        assert f'id="{element_id}" class="empty hidden" role="status"' in page.text
    assert 'class="empty analysis-empty hidden" role="status"' in page.text
    assert 'aria-labelledby="detail-title"' in page.text
    assert 'aria-labelledby="url-detail-title"' in page.text
    assert 'aria-labelledby="change-detail-title"' in page.text

    script = client.get("/ui/assets/app.js")
    assert script.status_code == 200
    assert "function renderTableState" in script.text
    assert "Wijzigingen konden niet worden geladen" in script.text
    assert "Vacatures konden niet worden geladen" in script.text
    assert "formatGoogleInspection" in script.text
    assert "/integrations/url_inspection/results" in script.text
    assert 'id="url-detail-google"' in page.text
    assert 'id="url-detail-hreflang"' in page.text


def test_issue_details_present_evidence_progressively(client: TestClient) -> None:
    page = client.get("/ui/assets/index.html")
    assert page.status_code == 200
    assert 'id="detail-evidence-summary"' in page.text
    assert 'id="detail-evidence-technical"' in page.text
    assert "Technische details tonen" in page.text
    assert 'id="broken-links-heading"' in page.text
    assert 'id="source-heading"' in page.text

    script = client.get("/ui/assets/app.js")
    assert script.status_code == 200
    assert "function renderIssueEvidence" in script.text
    assert 'source_page_count: "Unieke bronpagina’s"' in script.text
    assert "`Bronpagina’s met dit signaal (${sourceUrls.length})`" in script.text
    assert "evidencePresentationKeys" in script.text


def test_operations_page_has_responsive_process_states(client: TestClient) -> None:
    page = client.get("/ui/assets/index.html")
    assert page.status_code == 200
    assert 'id="crawl-capacity"' in page.text
    assert 'id="crawl-live-state"' in page.text
    assert 'id="start-issue-recalculation"' in page.text
    assert 'id="current-export-state"' in page.text
    assert 'id="crawl-run-cards"' in page.text
    assert 'id="crawl-failure-panel"' in page.text
    assert 'class="table-wrap operation-table-wrap"' in page.text
    assert "<th>Gevonden</th><th>Verwerkt</th>" in page.text
    for message_id in (
        "operations-load-message",
        "crawl-action-message",
        "export-action-message",
    ):
        assert f'id="{message_id}" class="operation-message" role="status"' in page.text

    script = client.get("/ui/assets/app.js")
    assert script.status_code == 200
    assert '"#crawl-run-cards"' in script.text
    assert "function crawlRunMetrics" in script.text
    assert "function showCrawlFailures" in script.text
    assert 'data-crawl-failures="' in script.text
    assert "Sitemapbestanden verwerkt" in script.text
    assert "URL's geïmporteerd" in script.text
    assert 'startCrawl("recalculate_issues")' in script.text
    assert "crawlworker${crawl.workers === 1" in script.text
    assert "`process-status ${crawlStatus}`" in script.text


def test_operations_status_ignores_stale_website_responses(client: TestClient) -> None:
    page = client.get("/ui/assets/index.html")
    assert page.status_code == 200
    assert 'src="/ui/assets/app.js?v=20260807-1"' in page.text
    assert 'href="/ui/assets/actionable.css?v=20260731-4"' in page.text
    assert 'id="recommendation-task-section"' in page.text
    assert 'id="recommendation-task-content"' in page.text
    assert 'id="tasks-view"' in page.text
    assert 'id="notification-popover"' in page.text
    assert 'href="/ui/assets/task-center.css?v=20260804-1"' in page.text
    assert 'href="/ui/assets/urls.css?v=20260804-1"' in page.text
    assert 'id="url-coverage-summary"' in page.text
    assert 'id="url-source-filter"' in page.text
    assert 'id="export-tasks"' in page.text

    script = client.get("/ui/assets/app.js")
    assert script.status_code == 200
    assert "Redirectbestemming gewijzigd naar homepage" in script.text
    assert "afhankelijke ${" in script.text
    assert "function canonicalHostSwap" in script.text
    assert "Websitebrede domeinverwisseling" in script.text
    assert "onderliggende wijzigingen" in script.text
    assert "const requestId = ++state.operationsRequestId;" in script.text
    assert (
        'requestId !== state.operationsRequestId || websiteId !== $("#website-select").value'
        in script.text
    )
    assert "state.activeCrawlJob = null;" in script.text
    assert "state.exports = [];" in script.text
    assert "function loadIssueRecommendation" in script.text
    assert "function loadTaskCenter" in script.text
    assert "function renderTaskNotifications" in script.text
    assert "function taskAssigneeOptions" in script.text
    assert 'id="recommendation-task-owner"' in script.text
    assert '<option value="">Niet toegewezen</option>' in script.text
    assert 'params.set("unassigned", "true")' in script.text
    assert "function renderUrlCoverage" in script.text
    assert "function exportTasks" in script.text
    assert "function createRecommendationTask" in script.text
    assert "function saveRecommendationTask" in script.text
    assert "function saveRecommendationFeedback" in script.text
    assert 'id="recommendation-feedback-form"' in script.text
    assert "Vrije opmerkingen worden nooit klantoverstijgend gebruikt" in script.text


def test_content_analysis_interface_exposes_evidence_and_coverage(client: TestClient) -> None:
    page = client.get("/ui/assets/index.html")
    assert page.status_code == 200
    assert 'id="content-analysis-nav"' in page.text
    assert 'id="content-analysis-view"' in page.text
    assert 'href="/ui/assets/content-analysis.css?v=20260807-1"' in page.text
    assert 'href="/ui/assets/opportunity-scores.css?v=20260807-1"' in page.text
    assert 'id="evaluate-opportunities"' in page.text
    for tab in ("overview", "pages", "clusters", "journey", "opportunities", "settings"):
        assert f'data-content-tab="{tab}"' in page.text
        assert f'id="content-tab-{tab}"' in page.text

    script = client.get("/ui/assets/app.js")
    assert script.status_code == 200
    assert 'contentAnalysis: "analyse/content"' in script.text
    assert "Promise.all([" in script.text
    assert "function renderContentAnalysis" in script.text
    assert "function loadContentAnalysis" in script.text
    assert "opportunityResult.milliseconds" in script.text
    assert "journeyResult.milliseconds" in script.text
    assert "coverage.transitions" in script.text
    assert "contentAnalysisPage" in script.text


def test_settings_and_integrations_have_responsive_states(client: TestClient) -> None:
    page = client.get("/ui/assets/index.html")
    assert page.status_code == 200
    assert 'id="client-cards"' in page.text
    assert 'id="member-cards"' in page.text
    assert 'class="table-wrap client-directory-table-wrap"' in page.text
    assert 'class="table-wrap member-table-wrap"' in page.text
    assert 'id="integration-message" class="integration-message hidden" role="status"' in page.text
    for element_id in [
        "matomo-connect",
        "matomo-server-url",
        "matomo-token",
        "matomo-property",
        "sync-matomo",
        "analytics-primary-source",
    ]:
        assert f'id="{element_id}"' in page.text

    script = client.get("/ui/assets/app.js")
    assert script.status_code == 200
    assert 'for (const selector of ["#client-rows", "#client-cards"])' in script.text
    assert 'for (const selector of ["#member-rows", "#member-cards"])' in script.text
    assert 'target.classList.toggle("connected"' in script.text
    assert 'connected: "Gekoppeld", error: "Fout"' in script.text
    assert "async function connectMatomo" in script.text
    assert "async function loadMatomoSites" in script.text
    assert "async function syncMatomo" in script.text
    assert "async function savePrimaryAnalyticsSource" in script.text


def test_dashboard_and_reports_have_clear_drilldowns(client: TestClient) -> None:
    page = client.get("/ui/assets/index.html")
    assert page.status_code == 200
    assert 'id="dashboard-priorities"' in page.text
    assert 'class="report-controls"' in page.text
    assert '<details id="report-archive"' in page.text
    assert page.text.index('id="report-archive"') > page.text.index('id="client-report"')
    assert 'data-report-period="month" class="active" aria-pressed="true"' in page.text

    script = client.get("/ui/assets/app.js")
    assert script.status_code == 200
    assert "data-dashboard-priority=" in script.text
    assert '"#dashboard-priorities"' in script.text
    assert "if (user.mfa_required)" in script.text
    assert "await openMfaSetup();" in script.text
    assert "if (!workspaceReady) return;" in script.text
    assert "Geen gekoppelde data" in script.text
    assert 'setAttribute("aria-pressed"' in script.text


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
    with SessionLocal() as db:
        failed_event = db.scalar(
            select(SecurityAuditEvent).where(
                SecurityAuditEvent.event_type == "authentication.login",
                SecurityAuditEvent.result == "failed",
            )
        )
        assert failed_event is not None
        assert failed_event.source_hash and len(failed_event.source_hash) == 64

    login = browser.post(
        "/ui/login",
        json={
            "email": "team@example.com",
            "password": "correct-horse-battery-staple",
        },
    )
    assert login.status_code == 204
    assert "HttpOnly" in login.headers["set-cookie"]
    assert f"Max-Age={ADMIN_SESSION_TTL_SECONDS}" in login.headers["set-cookie"]
    assert browser.get("/app").status_code == 200
    assert browser.get("/api/v1/clients").status_code == 200
    with SessionLocal() as db:
        succeeded_event = db.scalar(
            select(SecurityAuditEvent).where(
                SecurityAuditEvent.event_type == "authentication.login",
                SecurityAuditEvent.result == "succeeded",
            )
        )
        assert succeeded_event is not None
        assert succeeded_event.details == {"mfa_used": False}
    stolen_session = browser.cookies.get("seo_session")
    assert stolen_session

    assert browser.post("/ui/logout").status_code == 204
    assert browser.get("/api/v1/clients").status_code == 401
    replay = TestClient(app)
    replay.cookies.set("seo_session", stolen_session)
    assert replay.get("/api/v1/clients").status_code == 401


def test_session_duration_is_shorter_for_administrators() -> None:
    assert session_ttl_seconds("superuser") == 60 * 60 * 2
    assert session_ttl_seconds("admin") == ADMIN_SESSION_TTL_SECONDS
    assert session_ttl_seconds("user") == USER_SESSION_TTL_SECONDS
    assert session_ttl_seconds("client") == 60 * 60 * 12


def test_login_clears_session_for_missing_user() -> None:
    from app.main import app

    browser = TestClient(app)
    browser.cookies.set("seo_session", create_session_token(UUID(int=999)))
    response = browser.get("/login", follow_redirects=False)
    assert response.status_code == 200
    assert "seo_session=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]


def test_login_rate_limit_blocks_repeated_failures() -> None:
    from app.main import app

    browser = TestClient(app)
    for _ in range(5):
        response = browser.post(
            "/ui/login",
            json={"email": "unknown@example.com", "password": "wrong-password"},
        )
        assert response.status_code == 401
    blocked = browser.post(
        "/ui/login",
        json={"email": "unknown@example.com", "password": "wrong-password"},
    )
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "Probeer het later opnieuw"


def test_cookie_authenticated_mutation_rejects_foreign_origin() -> None:
    from app.main import app

    with SessionLocal() as db:
        user = User(
            email="csrf@example.com",
            role="admin",
            password_hash=hash_password("Csrf-secure-password-1!"),
        )
        db.add(user)
        db.commit()
    browser = TestClient(app)
    assert (
        browser.post(
            "/ui/login",
            json={"email": "csrf@example.com", "password": "Csrf-secure-password-1!"},
        ).status_code
        == 204
    )
    denied = browser.post("/ui/logout", headers={"Origin": "https://attacker.example"})
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Ongeldige request-origin"


def test_mfa_failures_are_rate_limited(monkeypatch) -> None:
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "1e" * 32)
    get_settings.cache_clear()
    from app.main import app

    with SessionLocal() as db:
        user = User(
            email="mfa-limit@example.com",
            role="admin",
            password_hash=hash_password("Mfa-limit-password-1!"),
            mfa_enabled=True,
        )
        db.add(user)
        db.commit()
    browser = TestClient(app)
    for _ in range(5):
        response = browser.post(
            "/ui/login",
            json={
                "email": "mfa-limit@example.com",
                "password": "Mfa-limit-password-1!",
                "mfa_code": "000000",
            },
        )
        assert response.status_code == 401
    assert (
        browser.post(
            "/ui/login",
            json={"email": "mfa-limit@example.com", "password": "Mfa-limit-password-1!"},
        ).status_code
        == 429
    )
    get_settings.cache_clear()


def test_admin_enrolls_mfa_and_uses_single_recovery_code(monkeypatch) -> None:
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "0e" * 32)
    monkeypatch.setenv("MFA_ENFORCEMENT_ENABLED", "true")
    get_settings.cache_clear()
    from app.main import app

    with SessionLocal() as db:
        user = User(
            email="mfa-admin@example.com",
            role="admin",
            password_hash=hash_password("Mfa-secure-password-1!"),
        )
        db.add(user)
        db.commit()
        user_id = user.id
    browser = TestClient(app)
    assert (
        browser.post(
            "/ui/login",
            json={"email": "mfa-admin@example.com", "password": "Mfa-secure-password-1!"},
        ).status_code
        == 204
    )
    assert browser.get("/api/v1/me").json()["mfa_required"] is True
    assert browser.get("/api/v1/clients").status_code == 428
    setup = browser.post("/api/v1/me/mfa/setup")
    setup_data = setup.json()
    assert setup.status_code == 200
    assert setup_data["qr_code_data_uri"].startswith("data:image/svg+xml;base64,")
    assert len(setup_data["recovery_codes"]) == 10
    assert (
        browser.post(
            "/api/v1/me/mfa/confirm",
            json={"code": totp_code(setup_data["secret"])},
        ).status_code
        == 204
    )
    assert browser.get("/api/v1/clients").status_code == 200
    recovery_code = setup_data["recovery_codes"][0]
    assert browser.post("/ui/logout").status_code == 204
    challenge = browser.post(
        "/ui/login",
        json={"email": "mfa-admin@example.com", "password": "Mfa-secure-password-1!"},
    )
    assert challenge.status_code == 202
    assert (
        browser.post(
            "/ui/login",
            json={
                "email": "mfa-admin@example.com",
                "password": "Mfa-secure-password-1!",
                "mfa_code": recovery_code,
            },
        ).status_code
        == 204
    )
    with SessionLocal() as db:
        enrolled = db.get(User, user_id)
        assert enrolled and enrolled.mfa_enabled
        assert len(enrolled.mfa_recovery_code_hashes) == 9
        mfa_events = list(
            db.scalars(
                select(SecurityAuditEvent).where(
                    SecurityAuditEvent.actor_user_id == user_id,
                    SecurityAuditEvent.event_type.in_({"mfa.setup_started", "mfa.enabled"}),
                )
            )
        )
        assert {event.event_type for event in mfa_events} == {
            "mfa.setup_started",
            "mfa.enabled",
        }
    get_settings.cache_clear()


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


def test_user_cannot_access_another_clients_website_data(client: TestClient) -> None:
    assigned = client.post("/api/v1/clients", json={"name": "Visible customer"}).json()
    hidden = client.post("/api/v1/clients", json={"name": "Private customer"}).json()
    visible_website = client.post(
        "/api/v1/websites",
        json={
            "client_id": assigned["id"],
            "name": "Visible site",
            "base_url": "https://visible.example.com",
        },
    ).json()
    hidden_website = client.post(
        "/api/v1/websites",
        json={
            "client_id": hidden["id"],
            "name": "Private site",
            "base_url": "https://private.example.com",
        },
    ).json()
    with SessionLocal() as db:
        user = User(
            email="isolated@example.com",
            role="user",
            password_hash=hash_password("isolated-secure-password"),
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
            json={"email": "isolated@example.com", "password": "isolated-secure-password"},
        ).status_code
        == 204
    )
    websites = browser.get("/api/v1/websites")
    assert websites.status_code == 200
    assert [website["id"] for website in websites.json()] == [visible_website["id"]]

    hidden_website_id = hidden_website["id"]
    protected_paths = [
        f"/api/v1/websites/{hidden_website_id}",
        f"/api/v1/websites/{hidden_website_id}/settings",
        f"/api/v1/websites/{hidden_website_id}/urls",
        f"/api/v1/websites/{hidden_website_id}/crawl-runs",
        f"/api/v1/websites/{hidden_website_id}/issues",
        f"/api/v1/websites/{hidden_website_id}/client-report",
    ]
    for path in protected_paths:
        assert browser.get(path).status_code == 403, path


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
    assert (
        browser.post(
            "/ui/login",
            json={"email": "client@example.com", "password": "client-secure-password"},
        ).status_code
        == 204
    )
    assert browser.get(f"/api/v1/websites/{website_id}/issues").status_code == 200
    assert (
        browser.patch(f"/api/v1/issues/{issue_id}", json={"status": "planned"}).status_code == 403
    )
    assert (
        browser.post(
            "/api/v1/exports",
            json={"website_id": str(website_id), "export_type": "excel"},
        ).status_code
        == 403
    )


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
    assert (
        browser.post(
            "/ui/login",
            json={"email": "admin@example.com", "password": "Admin-secure-password-1!"},
        ).status_code
        == 204
    )
    member_browser = TestClient(app)
    assert (
        member_browser.post(
            "/ui/login",
            json={"email": "managed@example.com", "password": "Managed-secure-password-1!"},
        ).status_code
        == 204
    )
    assert member_browser.get("/api/v1/me").status_code == 200
    assert (
        browser.patch(
            f"/api/v1/clients/{customer['id']}/members/{member_id}",
            json={"role": "admin"},
        ).status_code
        == 403
    )
    upgraded = browser.patch(
        f"/api/v1/clients/{customer['id']}/members/{member_id}",
        json={"role": "user"},
    )
    assert upgraded.status_code == 200
    assert upgraded.json()["client_role"] == "user"
    assert member_browser.get("/api/v1/me").status_code == 401
    assert (
        client.patch(
            f"/api/v1/clients/{customer['id']}/members/{admin_id}",
            json={"role": "user"},
        ).status_code
        == 409
    )
    assert (
        browser.patch(
            f"/api/v1/clients/{customer['id']}/members/{admin_id}",
            json={"role": "client"},
        ).status_code
        == 409
    )
    assert (
        browser.delete(f"/api/v1/clients/{customer['id']}/members/{member_id}").status_code == 204
    )
    with SessionLocal() as db:
        removed = db.get(User, member_id)
        assert removed and removed.is_active is False
        audit_events = list(
            db.scalars(
                select(SecurityAuditEvent).where(
                    SecurityAuditEvent.target_id == str(member_id),
                    SecurityAuditEvent.event_type.in_(
                        {"membership.role_changed", "membership.removed"}
                    ),
                )
            )
        )
        assert {event.event_type for event in audit_events} == {
            "membership.role_changed",
            "membership.removed",
        }
    reinvited = browser.post(
        "/api/v1/invitations",
        json={"email": "managed@example.com", "client_id": customer["id"], "role": "client"},
    )
    assert reinvited.status_code == 201
    token = reinvited.json()["accept_path"].split("token=", maxsplit=1)[1]
    accepted = TestClient(app).post(
        f"/api/v1/invitations/{token}/accept",
        json={"password": "Managed-secure-password-1!"},
    )
    assert accepted.status_code == 204
    with SessionLocal() as db:
        restored = db.get(User, member_id)
        membership = db.scalar(
            select(ClientMembership).where(ClientMembership.user_id == member_id)
        )
        assert restored and restored.is_active is True
        assert membership and membership.role == "client"


def test_invitation_cannot_replace_existing_account_password(client: TestClient) -> None:
    invited_client = client.post("/api/v1/clients", json={"name": "Invitation owner"}).json()
    existing_client = client.post("/api/v1/clients", json={"name": "Existing account"}).json()
    with SessionLocal() as db:
        admin = User(
            email="inviter@example.com",
            role="admin",
            password_hash=hash_password("Inviter-secure-password-1!"),
        )
        existing = User(
            email="existing@example.com",
            role="client",
            password_hash=hash_password("Existing-secure-password-1!"),
        )
        db.add_all([admin, existing])
        db.flush()
        db.add_all(
            [
                ClientMembership(
                    user_id=admin.id,
                    client_id=UUID(invited_client["id"]),
                    role="admin",
                ),
                ClientMembership(
                    user_id=existing.id,
                    client_id=UUID(existing_client["id"]),
                    role="client",
                ),
            ]
        )
        db.commit()
        existing_id = existing.id

    from app.main import app

    inviter = TestClient(app)
    assert (
        inviter.post(
            "/ui/login",
            json={"email": "inviter@example.com", "password": "Inviter-secure-password-1!"},
        ).status_code
        == 204
    )
    invitation = inviter.post(
        "/api/v1/invitations",
        json={
            "email": "existing@example.com",
            "client_id": invited_client["id"],
            "role": "client",
        },
    )
    token = invitation.json()["accept_path"].split("token=", maxsplit=1)[1]
    attack = TestClient(app).post(
        f"/api/v1/invitations/{token}/accept",
        json={"password": "Attacker-password-1!"},
    )
    assert attack.status_code == 409
    with SessionLocal() as db:
        existing = db.get(User, existing_id)
        assert existing is not None
        assert verify_password("Existing-secure-password-1!", existing.password_hash)
        assert not verify_password("Attacker-password-1!", existing.password_hash)


def test_tenant_client_role_cannot_write_when_user_is_admin_elsewhere(
    client: TestClient,
) -> None:
    admin_client = client.post("/api/v1/clients", json={"name": "Admin tenant"}).json()
    readonly_client = client.post("/api/v1/clients", json={"name": "Read-only tenant"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": readonly_client["id"],
            "name": "Read-only site",
            "base_url": "https://readonly.example.com",
        },
    ).json()
    with SessionLocal() as db:
        mixed_role_user = User(
            email="mixed-role@example.com",
            role="admin",
            password_hash=hash_password("Mixed-role-password-1!"),
        )
        db.add(mixed_role_user)
        db.flush()
        db.add_all(
            [
                ClientMembership(
                    user_id=mixed_role_user.id,
                    client_id=UUID(admin_client["id"]),
                    role="admin",
                ),
                ClientMembership(
                    user_id=mixed_role_user.id,
                    client_id=UUID(readonly_client["id"]),
                    role="client",
                ),
            ]
        )
        issue = Issue(
            website_id=UUID(website["id"]),
            issue_type="http_404",
            category="reachability",
            severity="high",
            title="Read-only issue",
            description="Mag niet worden gewijzigd.",
            recommended_action="Alleen bekijken.",
        )
        db.add(issue)
        db.commit()
        issue_id = issue.id

    from app.main import app

    browser = TestClient(app)
    assert (
        browser.post(
            "/ui/login",
            json={"email": "mixed-role@example.com", "password": "Mixed-role-password-1!"},
        ).status_code
        == 204
    )
    assert browser.get(f"/api/v1/websites/{website['id']}/issues").status_code == 200
    assert (
        browser.patch(f"/api/v1/issues/{issue_id}", json={"status": "planned"}).status_code == 403
    )
    assert (
        browser.post(
            "/api/v1/exports",
            json={"website_id": website["id"], "export_type": "excel"},
        ).status_code
        == 403
    )


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
        db.get(WebsiteSettings, website_id).primary_analytics_source = "ga4"
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
                    date=_period_dates("month", yesterday)[2],
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
    assert report.json()["primary_metric"] == "key_events"
    assert report.json()["comparison_context"] == "dezelfde dagen in de vorige maand"
    assert report.json()["search_insights"] == []


def test_report_ytd_and_half_year_use_year_over_year_windows() -> None:
    end = date(2026, 7, 12)
    half_year = _period_dates("half_year", end)
    ytd = _period_dates("ytd", end)

    assert half_year == (date(2026, 1, 12), end, date(2025, 1, 12), date(2025, 7, 12))
    assert ytd == (date(2026, 1, 1), end, date(2025, 1, 1), date(2025, 7, 12))


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
    assert detail.json()["scope"] == "seo"
    assert detail.json()["nature"] == "problem"
    assert detail.json()["source_urls"] == []
    assert detail.json()["guidance"]["likely_cause"] is None
    assert "volgende crawl" in detail.json()["guidance"]["verification"]
    assert detail.json()["guidance"]["sources"][0]["publisher"] == "Google Search Central"

    updated = client.patch(f"/api/v1/issues/{issue_id}", json={"status": "planned"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "planned"

    resolved = client.patch(f"/api/v1/issues/{issue_id}", json={"status": "resolved"})
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert client.get(f"/api/v1/websites/{website_id}/issues").json() == []
    history = client.get(f"/api/v1/websites/{website_id}/issues?status=all").json()
    assert len(history) == 1
    assert history[0]["status"] == "resolved"
    assert history[0]["scope"] == "seo"
    assert history[0]["nature"] == "problem"


def test_bulk_issue_actions_suppress_restore_and_audit(client: TestClient) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Bulk issues"}).json()
    website = client.post(
        "/api/v1/websites",
        json={"client_id": customer["id"], "name": "Bulk site", "base_url": "https://example.com"},
    ).json()
    website_id = UUID(website["id"])
    with SessionLocal() as db:
        url = Url(website_id=website_id, normalized_url="https://example.com/page")
        db.add(url)
        db.flush()
        first = Issue(
            website_id=website_id,
            url_id=url.id,
            issue_type="missing_title",
            category="onpage",
            severity="medium",
            title="Title ontbreekt",
            description="Test",
            recommended_action="Herstel",
        )
        second = Issue(
            website_id=website_id,
            url_id=url.id,
            issue_type="missing_description",
            category="onpage",
            severity="low",
            title="Beschrijving ontbreekt",
            description="Test",
            recommended_action="Herstel",
        )
        website_wide = Issue(
            website_id=website_id,
            url_id=None,
            issue_type="generic_internal_anchor_text",
            category="internal_links",
            severity="low",
            title="Generieke linkteksten",
            description="Test",
            recommended_action="Verbeter",
        )
        db.add_all([first, second, website_wide])
        db.commit()
        first_id, second_id, website_wide_id = first.id, second.id, website_wide.id

    response = client.post(
        f"/api/v1/websites/{website_id}/issues/bulk",
        json={
            "issue_ids": [str(first_id)],
            "action": "suppress_issue_type",
            "comment": "Bewuste uitzondering",
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "action": "suppress_issue_type",
        "updated_count": 1,
        "suppression_count": 1,
    }
    resolved = client.post(
        f"/api/v1/websites/{website_id}/issues/bulk",
        json={"issue_ids": [str(second_id)], "action": "resolve_and_recheck"},
    )
    assert resolved.status_code == 200
    wont_fix = client.post(
        f"/api/v1/websites/{website_id}/issues/bulk",
        json={
            "issue_ids": [str(website_wide_id)],
            "action": "wont_fix",
            "comment": "Bewuste websitebrede keuze",
        },
    )
    assert wont_fix.status_code == 200
    assert wont_fix.json()["updated_count"] == 1

    suppressions = client.get(f"/api/v1/websites/{website_id}/issue-suppressions").json()
    assert len(suppressions) == 1
    assert suppressions[0]["issue_type"] == "missing_title"
    suppression_id = suppressions[0]["id"]

    restored = client.post(
        f"/api/v1/websites/{website_id}/issue-suppressions/{suppression_id}/restore"
    )
    assert restored.status_code == 200
    assert restored.json()["is_active"] is False
    assert client.get(f"/api/v1/websites/{website_id}/issue-suppressions").json() == []
    with SessionLocal() as db:
        assert db.get(Issue, first_id).status == "new"
        assert db.get(Issue, second_id).status == "resolved"
        assert db.get(Issue, website_wide_id).status == "accepted_risk"
        suppression = db.get(IssueSuppression, UUID(suppression_id))
        assert suppression and suppression.restored_at is not None
        activities = list(
            db.scalars(select(ActivityLog).where(ActivityLog.website_id == website_id))
        )
        assert [item.activity_type for item in activities].count("issue_bulk_action") == 3
        assert any(item.activity_type == "issue_suppression_restored" for item in activities)


def test_issue_detail_returns_live_element_location(client: TestClient) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Element UI"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Element site",
            "base_url": "https://example.com",
        },
    ).json()
    website_id = UUID(website["id"])
    with SessionLocal() as db:
        source = Url(website_id=website_id, normalized_url="https://example.com/article")
        target = Url(
            website_id=website_id,
            normalized_url="https://example.com/missing",
            current_status_code=404,
        )
        job = CrawlJob(website_id=website_id, job_type="full_site_crawl")
        db.add_all([source, target, job])
        db.flush()
        run = CrawlRun(crawl_job_id=job.id, website_id=website_id, crawl_type="full_site_crawl")
        db.add(run)
        db.flush()
        snapshot = UrlSnapshot(
            url_id=source.id,
            crawl_run_id=run.id,
            requested_url=source.normalized_url,
            final_url=source.normalized_url,
            status_code=200,
            redirect_chain=[],
        )
        issue = Issue(
            website_id=website_id,
            url_id=target.id,
            issue_type="internally_linked_404",
            category="internal_links",
            severity="high",
            title="Interne link naar 404",
            description="Defect doel.",
            recommended_action="Werk de link bij.",
        )
        db.add_all([snapshot, issue])
        db.flush()
        db.add_all(
            [
                IssueOccurrence(
                    issue_id=issue.id,
                    crawl_run_id=run.id,
                    evidence={"incoming_internal_links": 1},
                ),
                ElementLocation(
                    website_id=website_id,
                    source_url_id=source.id,
                    snapshot_id=snapshot.id,
                    crawl_run_id=run.id,
                    issue_types=["internally_linked_404"],
                    element_type="a",
                    target_url=target.normalized_url,
                    visible_text="Oud artikel",
                    element_id="oude-link",
                    css_selector='a[id="oude-link"]',
                    xpath="/html/body/a[1]",
                    html_fragment='<a id="oude-link" href="/missing">Oud artikel</a>',
                    occurrence_index=1,
                    text_is_unique=True,
                    context_is_unique=True,
                    rendered_dynamically=False,
                ),
            ]
        )
        db.commit()
        issue_id = issue.id

    payload = client.get(f"/api/v1/issues/{issue_id}").json()
    assert len(payload["elements"]) == 1
    assert payload["elements"][0]["source_url"] == "https://example.com/article"
    assert payload["elements"][0]["jump_url"] == "https://example.com/article#oude-link"


def test_grouped_broken_links_use_latest_matching_element_evidence(client: TestClient) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Grouped elements"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Grouped element site",
            "base_url": "https://example.com",
        },
    ).json()
    website_id = UUID(website["id"])
    with SessionLocal() as db:
        source = Url(website_id=website_id, normalized_url="https://example.com/locaties")
        targets = [
            Url(website_id=website_id, normalized_url="https://example.com/missing-one"),
            Url(website_id=website_id, normalized_url="https://example.com/missing-two"),
        ]
        old_job = CrawlJob(website_id=website_id, job_type="full_site_crawl")
        current_job = CrawlJob(website_id=website_id, job_type="full_site_crawl")
        db.add_all([source, *targets, old_job, current_job])
        db.flush()
        old_run = CrawlRun(
            crawl_job_id=old_job.id,
            website_id=website_id,
            crawl_type="full_site_crawl",
        )
        current_run = CrawlRun(
            crawl_job_id=current_job.id,
            website_id=website_id,
            crawl_type="full_site_crawl",
        )
        db.add_all([old_run, current_run])
        db.flush()
        snapshot = UrlSnapshot(
            url_id=source.id,
            crawl_run_id=old_run.id,
            requested_url=source.normalized_url,
            final_url=source.normalized_url,
            status_code=200,
            redirect_chain=[],
        )
        issue = Issue(
            website_id=website_id,
            url_id=source.id,
            issue_type="multiple_broken_internal_links",
            category="internal_links",
            severity="high",
            title="2 dode interne links op deze pagina",
            description="Twee defecte links.",
            recommended_action="Werk beide links bij.",
        )
        db.add_all([snapshot, issue])
        db.flush()
        db.add(
            IssueOccurrence(
                issue_id=issue.id,
                crawl_run_id=current_run.id,
                evidence={
                    "broken_links": [
                        {"target_url": target.normalized_url, "anchor_text": f"Link {index}"}
                        for index, target in enumerate(targets, start=1)
                    ]
                },
            )
        )
        for index, target in enumerate(targets, start=1):
            db.add(
                ElementLocation(
                    website_id=website_id,
                    source_url_id=source.id,
                    snapshot_id=snapshot.id,
                    crawl_run_id=old_run.id,
                    issue_types=[],
                    element_type="a",
                    target_url=target.normalized_url,
                    visible_text=f"Link {index}",
                    css_selector=f"main > a:nth-of-type({index})",
                    xpath=f"/html/body/main/a[{index}]",
                    html_fragment=f'<a href="/missing-{index}">Link {index}</a>',
                    occurrence_index=index,
                    text_is_unique=True,
                    context_is_unique=True,
                    rendered_dynamically=False,
                )
            )
        db.commit()
        issue_id = issue.id

    elements = client.get(f"/api/v1/issues/{issue_id}").json()["elements"]
    assert [element["visible_text"] for element in elements] == ["Link 1", "Link 2"]
    assert all(element["jump_url"] for element in elements)


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
    monkeypatch.setenv("MFA_ENFORCEMENT_ENABLED", "true")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "11" * 32)
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
    monkeypatch.setenv("MFA_ENFORCEMENT_ENABLED", "true")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "12" * 32)
    get_settings.cache_clear()
    try:
        response = TestClient(app).get("/health")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200


def test_technical_api_key_is_rejected_in_production(monkeypatch) -> None:
    from app.main import app

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("API_KEY", "a-long-production-secret")
    monkeypatch.setenv("MFA_ENFORCEMENT_ENABLED", "true")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "13" * 32)
    get_settings.cache_clear()
    try:
        response = TestClient(app).get(
            "/api/v1/clients", headers={"X-API-Key": "a-long-production-secret"}
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 401


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
    active_job = client.get(f"/api/v1/websites/{website['id']}/crawl-jobs/active")
    assert active_job.status_code == 200
    assert active_job.json()["id"] == job.json()["id"]
    assert active_job.json()["queue_position"] is None
    assert active_job.json()["queue_depth"] == 0

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


def test_manual_url_registration_respects_excluded_patterns(client: TestClient) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Excluded discovery"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Excluded site",
            "base_url": "https://example.com",
        },
    ).json()
    settings = client.get(f"/api/v1/websites/{website['id']}/settings").json()
    settings["excluded_url_patterns"] = ["/search*"]
    updated = client.put(
        f"/api/v1/websites/{website['id']}/settings",
        json=settings,
    )
    assert updated.status_code == 200

    response = client.post(
        f"/api/v1/websites/{website['id']}/urls",
        json={"url": "https://example.com/search?filter=jobs"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "URL valt onder een uitgesloten URL-patroon"


def test_issue_list_hides_pagination_children_behind_series_review(client: TestClient) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Pagination UI"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Pagination site",
            "base_url": "https://example.com",
        },
    ).json()
    website_id = UUID(website["id"])
    with SessionLocal() as db:
        url = Url(
            website_id=website_id,
            normalized_url="https://example.com/articles?page=2",
        )
        job = CrawlJob(website_id=website_id, job_type="full_site_crawl")
        db.add_all([url, job])
        db.flush()
        run = CrawlRun(
            crawl_job_id=job.id,
            website_id=website_id,
            crawl_type="full_site_crawl",
        )
        child = Issue(
            website_id=website_id,
            url_id=url.id,
            issue_type="duplicate_title",
            category="onpage",
            severity="medium",
            title="Dubbele title",
            description="Herhaald pagineringssignaal.",
            recommended_action="Controleer de reeks.",
        )
        diagnosis = Issue(
            website_id=website_id,
            url_id=None,
            issue_type="pagination_series_review",
            category="indexation",
            severity="low",
            title="Pagineringsreeks",
            description="Gezamenlijke controle.",
            recommended_action="Controleer het template.",
        )
        db.add_all([run, child, diagnosis])
        db.flush()
        db.add(
            IssueOccurrence(
                issue_id=diagnosis.id,
                crawl_run_id=run.id,
                evidence={"patterns": [{"urls": [url.normalized_url]}]},
            )
        )
        db.commit()

    payload = client.get(f"/api/v1/websites/{website_id}/issues").json()

    assert [item["issue_type"] for item in payload] == ["pagination_series_review"]
    assert payload[0]["nature"] == "review"


def test_issue_list_hides_sitemap_redirects_covered_by_pattern_review(
    client: TestClient,
) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Sitemap UI"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Sitemap site",
            "base_url": "https://example.com",
        },
    ).json()
    website_id = UUID(website["id"])
    with SessionLocal() as db:
        url = Url(website_id=website_id, normalized_url="https://example.com/about")
        job = CrawlJob(website_id=website_id, job_type="full_site_crawl")
        db.add_all([url, job])
        db.flush()
        run = CrawlRun(
            crawl_job_id=job.id,
            website_id=website_id,
            crawl_type="full_site_crawl",
        )
        child = Issue(
            website_id=website_id,
            url_id=url.id,
            issue_type="sitemap_redirect",
            category="indexation",
            severity="medium",
            title="Sitemap-URL stuurt door",
            description="Los URL-signaal.",
            recommended_action="Gebruik de eind-URL.",
        )
        diagnosis = Issue(
            website_id=website_id,
            url_id=None,
            issue_type="sitemap_redirect_patterns",
            category="indexation",
            severity="medium",
            title="Vast sitemapredirectpatroon",
            description="Gezamenlijke controle.",
            recommended_action="Pas de sitemapgenerator aan.",
        )
        db.add_all([run, child, diagnosis])
        db.flush()
        db.add(
            IssueOccurrence(
                issue_id=diagnosis.id,
                crawl_run_id=run.id,
                evidence={"patterns": [{"urls": [url.normalized_url]}]},
            )
        )
        db.commit()

    payload = client.get(f"/api/v1/websites/{website_id}/issues").json()

    assert [item["issue_type"] for item in payload] == ["sitemap_redirect_patterns"]
    assert payload[0]["nature"] == "review"


def test_issue_list_hides_server_errors_covered_by_incident_review(
    client: TestClient,
) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Incident UI"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Incident site",
            "base_url": "https://example.com",
        },
    ).json()
    website_id = UUID(website["id"])
    with SessionLocal() as db:
        url = Url(website_id=website_id, normalized_url="https://example.com/unavailable")
        job = CrawlJob(website_id=website_id, job_type="full_site_crawl")
        db.add_all([url, job])
        db.flush()
        run = CrawlRun(
            crawl_job_id=job.id,
            website_id=website_id,
            crawl_type="full_site_crawl",
        )
        child = Issue(
            website_id=website_id,
            url_id=url.id,
            issue_type="http_5xx",
            category="reachability",
            severity="critical",
            title="Serverfout",
            description="Los URL-signaal.",
            recommended_action="Onderzoek de fout.",
        )
        diagnosis = Issue(
            website_id=website_id,
            url_id=None,
            issue_type="server_error_incident",
            category="reachability",
            severity="high",
            confidence="medium",
            title="Mogelijk serverincident",
            description="Gezamenlijke controle.",
            recommended_action="Bevestig met een light check.",
        )
        db.add_all([run, child, diagnosis])
        db.flush()
        db.add(
            IssueOccurrence(
                issue_id=diagnosis.id,
                crawl_run_id=run.id,
                evidence={"patterns": [{"urls": [url.normalized_url]}]},
            )
        )
        db.commit()

    payload = client.get(f"/api/v1/websites/{website_id}/issues").json()

    assert [item["issue_type"] for item in payload] == ["server_error_incident"]
    assert payload[0]["nature"] == "review"
    assert payload[0]["confidence"] == "medium"


def test_issue_list_hides_only_matching_children_behind_template_review(
    client: TestClient,
) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Template UI"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Template site",
            "base_url": "https://example.com",
        },
    ).json()
    website_id = UUID(website["id"])
    with SessionLocal() as db:
        url = Url(website_id=website_id, normalized_url="https://example.com/articles/one")
        unrelated_url = Url(
            website_id=website_id,
            normalized_url="https://example.com/articles/renamed",
        )
        legacy_url = Url(
            website_id=website_id,
            normalized_url="https://example.com/archive/legacy",
        )
        job = CrawlJob(website_id=website_id, job_type="full_site_crawl")
        db.add_all([url, unrelated_url, legacy_url, job])
        db.flush()
        run = CrawlRun(crawl_job_id=job.id, website_id=website_id, crawl_type="full_site_crawl")
        hidden = Issue(
            website_id=website_id,
            url_id=url.id,
            issue_type="deep_page",
            category="internal_links",
            severity="low",
            title="Diepe pagina",
            description="Templatepatroon.",
            recommended_action="Controleer de structuur.",
        )
        visible_same_key = Issue(
            website_id=website_id,
            url_id=unrelated_url.id,
            issue_type="deep_page",
            category="internal_links",
            severity="low",
            title="Los signaal op URL uit verouderd bewijs",
            description="Dit issue valt niet onder het cluster met een ander exact issue-ID.",
            recommended_action="Controleer dit afzonderlijk.",
        )
        visible = Issue(
            website_id=website_id,
            url_id=url.id,
            issue_type="http_404",
            category="reachability",
            severity="high",
            title="Pagina geeft 404",
            description="Los probleem.",
            recommended_action="Herstel de pagina.",
        )
        hidden_legacy = Issue(
            website_id=website_id,
            url_id=legacy_url.id,
            issue_type="orphan_page",
            category="internal_links",
            severity="medium",
            title="Orphan page",
            description="Legacy templatepatroon.",
            recommended_action="Controleer de structuur.",
        )
        diagnosis = Issue(
            website_id=website_id,
            url_id=None,
            issue_type="deep_page_clusters",
            category="onpage",
            severity="medium",
            title="Templateclusters",
            description="Gezamenlijke controle.",
            recommended_action="Controleer het template.",
        )
        legacy_diagnosis = Issue(
            website_id=website_id,
            url_id=None,
            issue_type="template_signal_clusters",
            category="onpage",
            severity="medium",
            title="Legacy templateclusters",
            description="Tijdelijke backwards compatibility.",
            recommended_action="Controleer het template.",
        )
        db.add_all(
            [
                run,
                hidden,
                visible_same_key,
                hidden_legacy,
                visible,
                diagnosis,
                legacy_diagnosis,
            ]
        )
        db.flush()
        db.add(
            IssueOccurrence(
                issue_id=diagnosis.id,
                crawl_run_id=run.id,
                evidence={
                    "clusters": [
                        {
                            "issue_type": "deep_page",
                            "issue_ids": [str(hidden.id)],
                            # Exact issue IDs are authoritative even when URL evidence
                            # has changed or been normalized differently.
                            "urls": [unrelated_url.normalized_url],
                        }
                    ]
                },
            )
        )
        db.add(
            IssueOccurrence(
                issue_id=legacy_diagnosis.id,
                crawl_run_id=run.id,
                evidence={
                    "clusters": [
                        {
                            "issue_type": "orphan_page",
                            "urls": [legacy_url.normalized_url],
                        }
                    ]
                },
            )
        )
        db.commit()

    payload = client.get(f"/api/v1/websites/{website_id}/issues").json()

    assert {item["title"] for item in payload} == {
        "Los signaal op URL uit verouderd bewijs",
        "Pagina geeft 404",
        "Templateclusters",
        "Legacy templateclusters",
    }


def test_issue_list_hides_redirect_targets_behind_source_page_group(client: TestClient) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Redirect UI"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Redirect site",
            "base_url": "https://example.com",
        },
    ).json()
    website_id = UUID(website["id"])
    with SessionLocal() as db:
        source = Url(website_id=website_id, normalized_url="https://example.com/article")
        target = Url(website_id=website_id, normalized_url="https://example.com/old")
        job = CrawlJob(website_id=website_id, job_type="full_site_crawl")
        db.add_all([source, target, job])
        db.flush()
        run = CrawlRun(
            crawl_job_id=job.id,
            website_id=website_id,
            crawl_type="full_site_crawl",
        )
        child = Issue(
            website_id=website_id,
            url_id=target.id,
            issue_type="internally_linked_redirect",
            category="internal_links",
            severity="medium",
            title="Interne links wijzen naar een redirect",
            description="Oud doel.",
            recommended_action="Werk de link bij.",
        )
        diagnosis = Issue(
            website_id=website_id,
            url_id=source.id,
            issue_type="multiple_redirected_internal_links",
            category="internal_links",
            severity="medium",
            title="2 interne links gaan via een redirect",
            description="Gezamenlijke broncontrole.",
            recommended_action="Werk beide links bij.",
        )
        db.add_all([run, child, diagnosis])
        db.flush()
        db.add(
            IssueOccurrence(
                issue_id=diagnosis.id,
                crawl_run_id=run.id,
                evidence={
                    "redirected_links": [
                        {
                            "redirect_url": target.normalized_url,
                            "final_url": "https://example.com/new",
                        }
                    ]
                },
            )
        )
        db.commit()

    payload = client.get(f"/api/v1/websites/{website_id}/issues").json()

    assert [item["issue_type"] for item in payload] == ["multiple_redirected_internal_links"]


def test_issue_list_hides_404_targets_behind_source_page_group(client: TestClient) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Broken-link UI"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Broken-link site",
            "base_url": "https://example.com",
        },
    ).json()
    website_id = UUID(website["id"])
    with SessionLocal() as db:
        source = Url(website_id=website_id, normalized_url="https://example.com/article")
        target = Url(website_id=website_id, normalized_url="https://example.com/missing")
        job = CrawlJob(website_id=website_id, job_type="full_site_crawl")
        db.add_all([source, target, job])
        db.flush()
        run = CrawlRun(crawl_job_id=job.id, website_id=website_id, crawl_type="full_site_crawl")
        child = Issue(
            website_id=website_id,
            url_id=target.id,
            issue_type="internally_linked_404",
            category="internal_links",
            severity="high",
            title="Interne link naar 404",
            description="Dood doel.",
            recommended_action="Werk de link bij.",
        )
        diagnosis = Issue(
            website_id=website_id,
            url_id=source.id,
            issue_type="multiple_broken_internal_links",
            category="internal_links",
            severity="high",
            title="Meerdere dode links",
            description="Gezamenlijke broncontrole.",
            recommended_action="Werk de links bij.",
        )
        db.add_all([run, child, diagnosis])
        db.flush()
        db.add(
            IssueOccurrence(
                issue_id=diagnosis.id,
                crawl_run_id=run.id,
                evidence={
                    "broken_links": [{"target_url": target.normalized_url, "status_code": 404}]
                },
            )
        )
        db.commit()

    payload = client.get(f"/api/v1/websites/{website_id}/issues").json()

    assert [item["issue_type"] for item in payload] == ["multiple_broken_internal_links"]


def test_running_crawl_can_pause_resume_and_cancel(client: TestClient) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Controlled crawl"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Controlled site",
            "base_url": "https://control.example.com",
        },
    ).json()
    created = client.post(
        "/api/v1/crawl-jobs",
        json={"website_id": website["id"], "job_type": "full_site_crawl"},
    ).json()
    job_id = created["id"]
    with SessionLocal() as db:
        job = db.get(CrawlJob, UUID(job_id))
        assert job
        job.status = "running"
        run = CrawlRun(
            crawl_job_id=job.id,
            website_id=job.website_id,
            crawl_type=job.job_type,
        )
        db.add(run)
        db.commit()

    pause = client.post(f"/api/v1/crawl-jobs/{job_id}/pause")
    assert pause.status_code == 200
    assert pause.json()["status"] == "pause_requested"

    with SessionLocal() as db:
        job = db.get(CrawlJob, UUID(job_id))
        run = db.scalar(select(CrawlRun).where(CrawlRun.crawl_job_id == UUID(job_id)))
        assert job and run
        job.status = "paused"
        run.status = "paused"
        db.commit()

    resume = client.post(f"/api/v1/crawl-jobs/{job_id}/resume")
    assert resume.status_code == 200
    assert resume.json()["status"] == "pending"

    cancel = client.post(f"/api/v1/crawl-jobs/{job_id}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"
    with SessionLocal() as db:
        run = db.scalar(select(CrawlRun).where(CrawlRun.crawl_job_id == UUID(job_id)))
        assert run and run.status == "cancelled" and run.finished_at is not None


def test_failed_crawl_without_saved_url_progress_cannot_resume(client: TestClient) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Failed crawl"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Failed site",
            "base_url": "https://failed.example.com",
        },
    ).json()
    created = client.post(
        "/api/v1/crawl-jobs",
        json={"website_id": website["id"], "job_type": "full_site_crawl"},
    ).json()
    job_id = created["id"]
    with SessionLocal() as db:
        job = db.get(CrawlJob, UUID(job_id))
        assert job
        job.status = "failed"
        db.add(
            CrawlRun(
                crawl_job_id=job.id,
                website_id=job.website_id,
                crawl_type=job.job_type,
                status="failed",
            )
        )
        db.commit()

    resume = client.post(f"/api/v1/crawl-jobs/{job_id}/resume")

    assert resume.status_code == 409
    assert resume.json()["detail"] == "Deze crawl heeft geen hervatbare voortgang"


def test_url_overview_hides_inactive_out_of_scope_records_by_default(
    client: TestClient,
) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Scoped URLs"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Pearle",
            "base_url": "https://www.pearle.nl",
        },
    ).json()
    endpoint = f"/api/v1/websites/{website['id']}/urls"
    created = client.post(endpoint, json={"url": "https://www.pearle.nl/winkels"}).json()

    with SessionLocal() as db:
        url = db.get(Url, UUID(created["id"]))
        assert url is not None
        url.is_active = False
        db.commit()

    assert client.get(endpoint).json() == []
    inactive = client.get(f"{endpoint}?active=false").json()
    assert [item["normalized_url"] for item in inactive] == ["https://www.pearle.nl/winkels"]


def test_url_overview_marks_depth_from_failed_crawl_as_unreliable(client: TestClient) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Depth context"}).json()
    website = client.post(
        "/api/v1/websites",
        json={"client_id": customer["id"], "name": "Depth", "base_url": "https://depth.test"},
    ).json()
    website_id = UUID(website["id"])
    with SessionLocal() as db:
        url = Url(website_id=website_id, normalized_url="https://depth.test/page", crawl_depth=2)
        job = CrawlJob(website_id=website_id, job_type="full_site_crawl", status="failed")
        db.add_all([url, job])
        db.flush()
        db.add(
            CrawlRun(
                crawl_job_id=job.id,
                website_id=website_id,
                crawl_type="full_site_crawl",
                status="failed",
            )
        )
        db.commit()

    item = client.get(f"/api/v1/websites/{website_id}/urls").json()[0]
    assert item["crawl_depth"] == 2
    assert item["crawl_depth_reliable"] is False
    assert "niet voltooid" in item["crawl_depth_context"]


def test_url_coverage_distinguishes_current_and_historical_sources(client: TestClient) -> None:
    customer = client.post("/api/v1/clients", json={"name": "URL coverage"}).json()
    website = client.post(
        "/api/v1/websites",
        json={"client_id": customer["id"], "name": "Coverage", "base_url": "https://coverage.test"},
    ).json()
    website_id = UUID(website["id"])
    crawl_started = datetime(2026, 8, 4, 10, tzinfo=UTC)
    with SessionLocal() as db:
        current = Url(website_id=website_id, normalized_url="https://coverage.test/current")
        historical = Url(website_id=website_id, normalized_url="https://coverage.test/historical")
        no_source = Url(website_id=website_id, normalized_url="https://coverage.test/no-source")
        job = CrawlJob(website_id=website_id, job_type="full_site_crawl", status="succeeded")
        db.add_all([current, historical, no_source, job])
        db.flush()
        db.add_all(
            [
                CrawlRun(
                    crawl_job_id=job.id,
                    website_id=website_id,
                    crawl_type="full_site_crawl",
                    status="succeeded",
                    started_at=crawl_started,
                ),
                UrlSource(
                    url_id=current.id,
                    source_type="sitemap",
                    source_url="https://coverage.test/sitemap.xml",
                    last_seen_at=crawl_started + timedelta(minutes=1),
                ),
                UrlSource(
                    url_id=current.id,
                    source_type="internal_link",
                    source_url="https://coverage.test/",
                    last_seen_at=crawl_started + timedelta(minutes=2),
                ),
                UrlSource(
                    url_id=historical.id,
                    source_type="sitemap",
                    source_url="https://coverage.test/sitemap.xml",
                    last_seen_at=crawl_started - timedelta(days=7),
                ),
            ]
        )
        db.commit()

    urls = client.get(f"/api/v1/websites/{website_id}/urls").json()
    by_path = {item["normalized_url"].rsplit("/", 1)[-1]: item for item in urls}
    assert by_path["current"]["current_source_types"] == ["internal_link", "sitemap"]
    assert by_path["historical"]["source_types"] == ["sitemap"]
    assert by_path["historical"]["current_source_types"] == []

    coverage = client.get(f"/api/v1/websites/{website_id}/url-coverage").json()
    assert coverage["reliable"] is True
    assert coverage["total_active_urls"] == 3
    assert coverage["current_source_counts"] == {"internal_link": 1, "sitemap": 1}
    assert coverage["multi_source_urls"] == 1
    assert coverage["historical_only_urls"] == 1
    assert coverage["no_source_urls"] == 1


def test_url_overview_includes_active_issue_summary(client: TestClient) -> None:
    customer = client.post("/api/v1/clients", json={"name": "URL signals"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Signals",
            "base_url": "https://signals.test",
        },
    ).json()
    website_id = UUID(website["id"])
    with SessionLocal() as db:
        url = Url(
            website_id=website_id,
            normalized_url="https://signals.test/empty",
            current_status_code=200,
        )
        db.add(url)
        db.flush()
        db.add_all(
            [
                Issue(
                    website_id=website_id,
                    url_id=url.id,
                    issue_type="thin_content",
                    category="onpage",
                    severity="medium",
                    status="new",
                    title="Nagenoeg lege pagina",
                    description="De pagina bevat nauwelijks hoofdcontent.",
                    recommended_action="Controleer of deze pagina live hoort te staan.",
                ),
                Issue(
                    website_id=website_id,
                    url_id=url.id,
                    issue_type="missing_meta_description",
                    category="onpage",
                    severity="low",
                    status="resolved",
                    title="Meta description ontbreekt",
                    description="Ontbreekt.",
                    recommended_action="Voeg toe.",
                ),
            ]
        )
        db.commit()

    item = client.get(f"/api/v1/websites/{website_id}/urls").json()[0]
    assert item["active_issue_count"] == 1
    assert item["highest_issue_severity"] == "medium"
    assert item["active_issue_titles"] == ["Nagenoeg lege pagina"]


def test_url_detail_returns_shortest_internal_route(client: TestClient) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Route context"}).json()
    website = client.post(
        "/api/v1/websites",
        json={"client_id": customer["id"], "name": "Route", "base_url": "https://route.test"},
    ).json()
    website_id = UUID(website["id"])
    with SessionLocal() as db:
        root = Url(website_id=website_id, normalized_url="https://route.test/", crawl_depth=0)
        middle = Url(website_id=website_id, normalized_url="https://route.test/hub", crawl_depth=1)
        target = Url(website_id=website_id, normalized_url="https://route.test/page", crawl_depth=2)
        job = CrawlJob(website_id=website_id, job_type="full_site_crawl", status="succeeded")
        db.add_all([root, middle, target, job])
        db.flush()
        run = CrawlRun(
            crawl_job_id=job.id,
            website_id=website_id,
            crawl_type="full_site_crawl",
            status="succeeded",
        )
        db.add(run)
        db.flush()
        db.add_all(
            [
                UrlLink(
                    crawl_run_id=run.id,
                    source_url_id=root.id,
                    target_url=middle.normalized_url,
                    target_url_id=middle.id,
                    is_internal=True,
                    is_nofollow=False,
                ),
                UrlLink(
                    crawl_run_id=run.id,
                    source_url_id=middle.id,
                    target_url=target.normalized_url,
                    target_url_id=target.id,
                    is_internal=True,
                    is_nofollow=False,
                ),
            ]
        )
        db.commit()
        target_id = target.id

    route = client.get(f"/api/v1/urls/{target_id}/crawl-route").json()
    assert route["reliable"] is True
    assert route["route"] == [
        "https://route.test/",
        "https://route.test/hub",
        "https://route.test/page",
    ]

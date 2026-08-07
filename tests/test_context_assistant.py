from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun
from app.models.discovery import CrawlJob, Url
from app.models.integrations import (
    GoogleAnalyticsLandingPageEventMetric,
    GoogleAnalyticsMetric,
    IntegrationConnection,
    WebsiteIntegration,
)
from app.models.issues import ActivityLog, Issue, IssueOccurrence
from app.models.recommendations import RecommendationTask
from app.models.user import ClientMembership, User
from app.models.website import Website, WebsiteSettings
from app.services.opportunity_scoring import (
    calculate_opportunity_scores,
    store_opportunity_evaluation,
)


def test_context_assistant_is_read_only_deterministic_and_tenant_bound(
    client: TestClient,
) -> None:
    with SessionLocal() as db:
        allowed_client = Client(name="Context assistant tenant")
        hidden_client = Client(name="Hidden context assistant tenant")
        db.add_all([allowed_client, hidden_client])
        db.flush()
        allowed_site = Website(
            client_id=allowed_client.id,
            name="Context site",
            base_url="https://context.example.com",
        )
        hidden_site = Website(
            client_id=hidden_client.id,
            name="Hidden context site",
            base_url="https://hidden-context.example.com",
        )
        user = User(
            email="context-reader@example.com",
            role="user",
            password_hash=hash_password("context-reader-password"),
        )
        db.add_all([allowed_site, hidden_site, user])
        db.flush()
        db.add(ClientMembership(user_id=user.id, client_id=allowed_client.id, role="user"))
        url = Url(
            website_id=allowed_site.id,
            normalized_url="https://context.example.com/page",
        )
        hidden_url = Url(
            website_id=hidden_site.id,
            normalized_url="https://hidden-context.example.com/page",
        )
        db.add_all([url, hidden_url])
        db.flush()
        issue = Issue(
            website_id=allowed_site.id,
            url_id=url.id,
            issue_type="missing_title",
            category="onpage",
            severity="medium",
            confidence="high",
            title="Title ontbreekt",
            description="De pagina heeft geen title.",
            recommended_action="Voeg een unieke title toe.",
        )
        hidden_issue = Issue(
            website_id=hidden_site.id,
            url_id=hidden_url.id,
            issue_type="missing_title",
            category="onpage",
            severity="medium",
            confidence="high",
            title="Verborgen title ontbreekt",
            description="Verborgen klantdata.",
            recommended_action="Verborgen actie.",
        )
        db.add_all([issue, hidden_issue])
        db.flush()
        issue_without_evidence = Issue(
            website_id=allowed_site.id,
            url_id=None,
            issue_type="missing_meta_description",
            category="onpage",
            severity="low",
            confidence="medium",
            title="Description ontbreekt",
            description="Er is nog geen afzonderlijke waarneming.",
            recommended_action="Controleer de pagina.",
        )
        job = CrawlJob(
            website_id=allowed_site.id,
            job_type="full_site_crawl",
            status="succeeded",
        )
        db.add_all([issue_without_evidence, job])
        db.flush()
        run = CrawlRun(
            crawl_job_id=job.id,
            website_id=allowed_site.id,
            crawl_type="full_site_crawl",
            status="succeeded",
        )
        db.add(run)
        db.flush()
        db.add(
            IssueOccurrence(
                issue_id=issue.id,
                crawl_run_id=run.id,
                evidence={"verification": "de volgende crawl vindt een unieke title"},
            )
        )
        evaluation, _ = store_opportunity_evaluation(
            db,
            website_id=allowed_site.id,
            primary_url_id=url.id,
            scope_type="page",
            scope_key=f"ctr:{url.id}",
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 28),
            scores=calculate_opportunity_scores(
                potential=80, friction=70, evidence=75, feasibility=60
            ),
            source_coverage={
                "gsc": True,
                "crawler_issues": True,
                "analytics": False,
                "pattern": "ctr",
            },
            contributors=[{"dimension": "potential", "signal": "gsc_impressions", "value": 500}],
            evidence=[{"source": "gsc", "impressions": 500}],
        )
        db.commit()
        allowed_site_id = allowed_site.id
        hidden_site_id = hidden_site.id
        issue_id = issue.id
        issue_without_evidence_id = issue_without_evidence.id
        hidden_issue_id = hidden_issue.id
        evaluation_id = evaluation.id

    from app.main import app

    browser = TestClient(app)
    assert (
        browser.post(
            "/ui/login",
            json={
                "email": "context-reader@example.com",
                "password": "context-reader-password",
            },
        ).status_code
        == 204
    )
    payload = {
        "question": "Wat betekent dit issue en wat moet ik controleren?",
        "context_type": "issue",
        "context_id": str(issue_id),
    }
    first = browser.post(
        f"/api/v1/websites/{allowed_site_id}/context-assistant/answer", json=payload
    )
    second = browser.post(
        f"/api/v1/websites/{allowed_site_id}/context-assistant/answer", json=payload
    )
    assert first.status_code == 200
    assert first.json() == second.json()
    assert first.json()["status"] == "answered"
    assert first.json()["mutations_performed"] is False
    assert first.json()["sources"][0]["record_id"] == str(issue_id)
    assert first.json()["missing_evidence"] == []
    assert [item["source_type"] for item in first.json()["sources"]] == [
        "issue",
        "issue_occurrence",
    ]

    missing = browser.post(
        f"/api/v1/websites/{allowed_site_id}/context-assistant/answer",
        json={**payload, "context_id": str(issue_without_evidence_id)},
    )
    assert missing.status_code == 200
    assert missing.json()["status"] == "insufficient_evidence"
    assert "geen afzonderlijk meetrecord" in missing.json()["missing_evidence"][0]

    opportunity = browser.post(
        f"/api/v1/websites/{allowed_site_id}/context-assistant/answer",
        json={
            "question": "Waarom heeft deze kans deze prioriteit?",
            "context_type": "opportunity_evaluation",
            "context_id": str(evaluation_id),
        },
    )
    assert opportunity.status_code == 200
    assert opportunity.json()["status"] == "answered"
    assert any(
        "Bron analytics ontbreekt" in item for item in opportunity.json()["missing_evidence"]
    )
    assert opportunity.json()["confidence"] == "high"

    limited = browser.post(
        f"/api/v1/websites/{allowed_site_id}/context-assistant/answer",
        json={**payload, "question": "Welke andere tool is beter dan Semrush?"},
    )
    assert limited.status_code == 200
    assert limited.json()["status"] == "scope_limited"
    assert limited.json()["sources"] == []

    assert (
        browser.post(
            f"/api/v1/websites/{allowed_site_id}/context-assistant/answer",
            json={**payload, "context_id": str(hidden_issue_id)},
        ).status_code
        == 404
    )
    assert (
        browser.post(
            f"/api/v1/websites/{hidden_site_id}/context-assistant/answer",
            json={**payload, "context_id": str(hidden_issue_id)},
        ).status_code
        == 403
    )

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(RecommendationTask)) == 0
        assert db.scalar(select(func.count()).select_from(ActivityLog)) == 0
        assert db.scalar(select(func.count()).select_from(CrawlJob)) == 1


def test_context_assistant_compares_leads_and_page_drivers(client: TestClient) -> None:
    with SessionLocal() as db:
        customer = Client(name="Performance context tenant")
        website = Website(
            client=customer,
            name="Performance context site",
            base_url="https://performance-context.example.com",
        )
        website.settings = WebsiteSettings(primary_analytics_source="ga4")
        db.add_all([customer, website])
        db.flush()
        first_page = Url(
            website_id=website.id,
            normalized_url="https://performance-context.example.com/growing",
        )
        second_page = Url(
            website_id=website.id,
            normalized_url="https://performance-context.example.com/declining",
        )
        anomaly_page = Url(
            website_id=website.id,
            normalized_url="https://performance-context.example.com/newsletter",
        )
        connection = IntegrationConnection(
            client_id=customer.id,
            provider="google",
            status="connected",
        )
        db.add_all([first_page, second_page, anomaly_page, connection])
        db.flush()
        db.add(
            WebsiteIntegration(
                website_id=website.id,
                connection_id=connection.id,
                service="ga4",
                external_property_id="properties/context",
                status="active",
                settings={"qualified_key_events": ["lead", "newsletter"]},
            )
        )
        rows = [
            (date(2025, 7, 1), first_page, 80, 4),
            (date(2025, 7, 28), second_page, 20, 1),
            (date(2026, 6, 3), first_page, 100, 5),
            (date(2026, 6, 30), second_page, 100, 4),
            (date(2026, 7, 1), first_page, 100, 10),
            (date(2026, 7, 28), second_page, 50, 1),
            (date(2026, 7, 28), anomaly_page, 2, 0),
        ]
        db.add_all(
            GoogleAnalyticsMetric(
                website_id=website.id,
                url_id=page.id,
                date=metric_date,
                landing_page=page.normalized_url,
                sessions=sessions,
                active_users=sessions,
                key_events=leads + 100,
            )
            for metric_date, page, sessions, leads in rows
        )
        db.add_all(
            GoogleAnalyticsLandingPageEventMetric(
                website_id=website.id,
                url_id=page.id,
                date=metric_date,
                landing_page=page.normalized_url,
                event_name="lead",
                key_events=leads,
            )
            for metric_date, page, _sessions, leads in rows
            if leads
        )
        db.commit()
        website_id = website.id

    response = client.post(
        f"/api/v1/websites/{website_id}/context-assistant/answer",
        json={
            "question": "Waardoor zijn organische leads veranderd?",
            "context_type": "website_performance",
            "context_id": str(website_id),
            "period_end": "2026-07-28",
            "days": 28,
        },
    )
    assert response.status_code == 200
    answer = response.json()
    assert answer["status"] == "answered"
    assert "van 9.0 naar 11.0" in answer["answer"]
    assert any("conversieratio" in item for item in answer["interpretations"])
    assert any("growing" in item for item in answer["interpretations"])
    assert any("declining" in item and "verkeer" in item for item in answer["interpretations"])
    assert any("twee jaar eerder" in item for item in answer["missing_evidence"])
    assert any("één jaar eerder" in item and "5.0 leads" in item for item in answer["facts"])
    assert "geen causaliteit" in answer["answer"]
    assert answer["mutations_performed"] is False

    missing_period = client.post(
        f"/api/v1/websites/{website_id}/context-assistant/answer",
        json={
            "question": "Vergelijk de leads",
            "context_type": "website_performance",
            "context_id": str(website_id),
        },
    )
    assert missing_period.status_code == 422
    mismatched_context = client.post(
        f"/api/v1/websites/{website_id}/context-assistant/answer",
        json={
            "question": "Vergelijk de leads",
            "context_type": "website_performance",
            "context_id": str(uuid4()),
            "period_end": "2026-07-28",
        },
    )
    assert mismatched_context.status_code == 404

    with SessionLocal() as db:
        db.add(
            GoogleAnalyticsLandingPageEventMetric(
                website_id=website_id,
                url_id=db.scalar(select(Url.id).where(Url.normalized_url.endswith("/newsletter"))),
                date=date(2026, 7, 28),
                landing_page="https://performance-context.example.com/newsletter",
                event_name="newsletter",
                key_events=20,
            )
        )
        db.commit()
    quality_warning = client.post(
        f"/api/v1/websites/{website_id}/context-assistant/answer",
        json={
            "question": "Waardoor zijn organische leads veranderd?",
            "context_type": "website_performance",
            "context_id": str(website_id),
            "period_end": "2026-07-28",
            "days": 28,
        },
    )
    assert quality_warning.status_code == 200
    warning = quality_warning.json()
    assert warning["confidence"] == "low"
    assert "ruwe leads van 9.0 naar 31.0" in warning["answer"]
    assert "zonder verdachte bijdragen is dit 9.0 naar 11.0" in warning["answer"]
    assert "geen leadconclusie" in warning["answer"]
    assert any("20.0 events bij 2 sessies" in item for item in warning["interpretations"])
    assert any("niet verwijderd" in item for item in warning["interpretations"])

    with SessionLocal() as db:
        stored_newsletter_events = db.scalar(
            select(GoogleAnalyticsLandingPageEventMetric.key_events).where(
                GoogleAnalyticsLandingPageEventMetric.event_name == "newsletter"
            )
        )
    assert stored_newsletter_events == 20

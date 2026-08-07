from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.client import Client
from app.models.discovery import Url
from app.models.user import ClientMembership, User
from app.models.website import Website
from app.services.opportunity_scoring import (
    FORMULA_VERSION,
    calculate_opportunity_scores,
    store_opportunity_evaluation,
)


def test_scoring_is_explainable_and_evidence_limited() -> None:
    high = calculate_opportunity_scores(potential=90, friction=80, evidence=90, feasibility=80)
    assert high.total == 86.0
    assert high.priority_class == "high_opportunity"

    limited = calculate_opportunity_scores(
        potential=100, friction=100, evidence=39, feasibility=100
    )
    assert limited.total == 39.99
    assert limited.priority_class == "insufficient_evidence"

    unknown = calculate_opportunity_scores(potential=80, friction=None, evidence=80, feasibility=70)
    assert unknown.total is None
    assert unknown.priority_class == "insufficient_evidence"
    with pytest.raises(ValueError, match="between zero and one hundred"):
        calculate_opportunity_scores(potential=101, friction=50, evidence=50, feasibility=50)


def test_evaluation_is_historical_idempotent_and_tenant_bound(client: TestClient) -> None:
    with SessionLocal() as db:
        allowed_client = Client(name="Allowed opportunity tenant")
        hidden_client = Client(name="Hidden opportunity tenant")
        db.add_all([allowed_client, hidden_client])
        db.flush()
        allowed_site = Website(
            client_id=allowed_client.id,
            name="Allowed opportunity site",
            base_url="https://allowed-opportunity.example.com",
        )
        hidden_site = Website(
            client_id=hidden_client.id,
            name="Hidden opportunity site",
            base_url="https://hidden-opportunity.example.com",
        )
        user = User(
            email="opportunity-reader@example.com",
            role="user",
            password_hash=hash_password("opportunity-reader-password"),
        )
        db.add_all([allowed_site, hidden_site, user])
        db.flush()
        db.add(ClientMembership(user_id=user.id, client_id=allowed_client.id, role="user"))
        url = Url(
            website_id=allowed_site.id,
            normalized_url="https://allowed-opportunity.example.com/page",
        )
        db.add(url)
        db.flush()
        scores = calculate_opportunity_scores(
            potential=80, friction=70, evidence=75, feasibility=60
        )
        first, created = store_opportunity_evaluation(
            db,
            website_id=allowed_site.id,
            primary_url_id=url.id,
            scope_type="page",
            scope_key=str(url.id),
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 28),
            scores=scores,
            source_coverage={"gsc": True, "analytics": False},
            contributors=[{"dimension": "potential", "signal": "gsc_impressions", "value": 80}],
            evidence=[{"source": "gsc", "period_days": 28}],
        )
        duplicate, duplicate_created = store_opportunity_evaluation(
            db,
            website_id=allowed_site.id,
            primary_url_id=url.id,
            scope_type="page",
            scope_key=str(url.id),
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 28),
            scores=scores,
            source_coverage={"gsc": True, "analytics": False},
            contributors=[{"dimension": "potential", "signal": "gsc_impressions", "value": 80}],
            evidence=[{"source": "gsc", "period_days": 28}],
        )
        db.commit()
        allowed_site_id = allowed_site.id
        hidden_site_id = hidden_site.id
        assert created is True and duplicate_created is False and first.id == duplicate.id
        assert first.formula_version == FORMULA_VERSION

    from app.main import app

    browser = TestClient(app)
    assert (
        browser.post(
            "/ui/login",
            json={
                "email": "opportunity-reader@example.com",
                "password": "opportunity-reader-password",
            },
        ).status_code
        == 204
    )
    response = browser.get(f"/api/v1/websites/{allowed_site_id}/opportunity-evaluations")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["formula_version"] == FORMULA_VERSION
    assert (
        browser.get(f"/api/v1/websites/{hidden_site_id}/opportunity-evaluations").status_code == 403
    )

from datetime import UTC, datetime, timedelta

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.external_intelligence import (
    ExternalObservation,
    ExternalUsageRecord,
)
from app.models.website import Website, WebsiteSettings
from app.services.external_intelligence.contracts import QuestionEvidenceRequest
from app.services.external_intelligence.policy import admit_external_request

NOW = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)


def context(question: str = "wat kosten kunststof kozijnen") -> QuestionEvidenceRequest:
    return QuestionEvidenceRequest(
        question=question,
        language="nl",
        country="NL",
        device="mobile",
        location="Nederland",
    )


def website_with_policy(
    db,  # type: ignore[no-untyped-def]
    *,
    enabled: bool = True,
    budget: int = 10_000,
    scopes: int = 5,
) -> Website:
    client = Client(name="External intelligence client")
    website = Website(
        client=client,
        name="External intelligence site",
        base_url=f"https://external-{id(client)}.example.com",
        settings=WebsiteSettings(
            external_intelligence_enabled=enabled,
            external_monthly_budget_micros=budget,
            external_active_scope_limit=scopes,
        ),
    )
    db.add(website)
    db.flush()
    return website


def admit(db, website: Website, **overrides):  # type: ignore[no-untyped-def]
    values = {
        "website_id": website.id,
        "url_id": None,
        "capability": "ai_citations",
        "context": context(),
        "reason": "question_gap",
        "provider": "fixture",
        "estimated_cost_micros": 500,
        "now": NOW,
    }
    values.update(overrides)
    return admit_external_request(db, **values)


def test_feature_is_disabled_by_default() -> None:
    with SessionLocal() as db:
        website = website_with_policy(db, enabled=False)

        admission = admit(db, website)

    assert admission.status == "disabled"
    assert admission.request is None


def test_same_daily_request_is_idempotent() -> None:
    with SessionLocal() as db:
        website = website_with_policy(db)

        first = admit(db, website)
        second = admit(db, website)

    assert first.status == "created"
    assert second.status == "duplicate"
    assert first.request is not None and second.request is not None
    assert first.request.id == second.request.id


def test_fresh_observation_prevents_a_new_paid_request() -> None:
    with SessionLocal() as db:
        website = website_with_policy(db)
        first = admit(db, website)
        assert first.request is not None
        observation = ExternalObservation(
            website_id=website.id,
            request_id=first.request.id,
            capability="ai_citations",
            cache_key=context().cache_key,
            provider="fixture",
            observed_at=NOW,
            expires_at=NOW + timedelta(days=7),
            input_hash="a" * 64,
            evidence_hash="b" * 64,
            normalized_payload={"sources": []},
            source_coverage={"ai_citations": True},
        )
        first.request.status = "succeeded"
        db.add(observation)
        db.flush()

        cached = admit(db, website, now=NOW + timedelta(days=1))

    assert cached.status == "cached"
    assert cached.observation is observation


def test_pending_reservations_cannot_overspend_budget() -> None:
    with SessionLocal() as db:
        website = website_with_policy(db, budget=800)
        first = admit(db, website, estimated_cost_micros=600)

        blocked = admit(
            db,
            website,
            context=context("hoe lang gaan kunststof kozijnen mee"),
            estimated_cost_micros=300,
        )

    assert first.status == "created"
    assert blocked.status == "budget_exceeded"
    assert blocked.reserved_micros == 600


def test_recorded_monthly_cost_blocks_later_request() -> None:
    with SessionLocal() as db:
        website = website_with_policy(db, budget=1_000)
        first = admit(db, website, estimated_cost_micros=700)
        assert first.request is not None
        first.request.status = "succeeded"
        db.add(
            ExternalUsageRecord(
                website_id=website.id,
                request_id=first.request.id,
                capability="ai_citations",
                provider="fixture",
                units=1,
                estimated_cost_micros=700,
                actual_cost_micros=800,
                recorded_at=NOW,
            )
        )
        db.flush()

        blocked = admit(
            db,
            website,
            context=context("hoe lang gaan kunststof kozijnen mee"),
            estimated_cost_micros=300,
        )

    assert blocked.status == "budget_exceeded"
    assert blocked.spent_micros == 800


def test_scope_limit_applies_to_distinct_questions() -> None:
    with SessionLocal() as db:
        website = website_with_policy(db, scopes=1)
        assert admit(db, website).status == "created"

        blocked = admit(
            db,
            website,
            context=context("hoe lang gaan kunststof kozijnen mee"),
        )

    assert blocked.status == "scope_limit_reached"


def test_idempotency_is_tenant_bound() -> None:
    with SessionLocal() as db:
        first_site = website_with_policy(db)
        second_site = website_with_policy(db)

        first = admit(db, first_site)
        second = admit(db, second_site)

    assert first.status == "created"
    assert second.status == "created"
    assert first.request is not None and second.request is not None
    assert first.request.id != second.request.id


def test_observation_cannot_reference_another_tenants_request() -> None:
    tenant_constraint = next(
        constraint
        for constraint in ExternalObservation.__table__.foreign_key_constraints
        if constraint.name == "fk_external_observation_request_tenant"
    )

    assert {column.name for column in tenant_constraint.columns} == {"request_id", "website_id"}
    assert {element.target_fullname for element in tenant_constraint.elements} == {
        "external_intelligence_requests.id",
        "external_intelligence_requests.website_id",
    }

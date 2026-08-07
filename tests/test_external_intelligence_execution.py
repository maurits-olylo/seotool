import asyncio
from datetime import UTC, datetime

import pytest

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.external_intelligence import (
    ExternalIntelligenceRequest,
    ExternalObservation,
    ExternalUsageRecord,
)
from app.models.website import Website, WebsiteSettings
from app.services.external_intelligence.contracts import (
    AiCitationObservation,
    ProviderUsage,
    QuestionEvidenceRequest,
    SerpObservation,
    SourceReference,
)
from app.services.external_intelligence.execution import execute_external_request
from app.services.external_intelligence.policy import admit_external_request
from app.services.external_intelligence.providers.dataforseo import DataForSeoResponseError

NOW = datetime(2026, 8, 8, 14, 0, tzinfo=UTC)


class FakeProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def fetch_serp(
        self, request: QuestionEvidenceRequest
    ) -> tuple[SerpObservation, ProviderUsage]:
        raise AssertionError("SERP was not expected")

    async def fetch_citations(
        self, request: QuestionEvidenceRequest
    ) -> tuple[tuple[AiCitationObservation, ...], ProviderUsage]:
        self.calls += 1
        if self.fail:
            raise DataForSeoResponseError("synthetic provider failure")
        return (
            (
                AiCitationObservation(
                    provider="fixture",
                    observed_at=NOW,
                    request=request,
                    platform="google_ai_overview",
                    observed_question="Wat kosten kunststof kozijnen gemiddeld?",
                    sources=(SourceReference(url="https://bron.example/prijzen"),),
                ),
            ),
            ProviderUsage(provider="fixture", cost_micros=750),
        )


def admitted_request(db) -> ExternalIntelligenceRequest:  # type: ignore[no-untyped-def]
    website = Website(
        client=Client(name="Execution client"),
        name="Execution site",
        base_url="https://execution.example",
        settings=WebsiteSettings(
            external_intelligence_enabled=True,
            external_monthly_budget_micros=10_000,
            external_active_scope_limit=5,
        ),
    )
    db.add(website)
    db.flush()
    admission = admit_external_request(
        db,
        website_id=website.id,
        url_id=None,
        capability="ai_citations",
        context=QuestionEvidenceRequest(
            question="wat kosten kunststof kozijnen",
            language="nl",
            country="NL",
            device="mobile",
            location="Nederland",
        ),
        reason="human_selected_question",
        provider="fixture",
        estimated_cost_micros=800,
        now=NOW,
    )
    assert admission.request is not None
    db.commit()
    return admission.request


def test_execution_atomically_stores_normalized_evidence_and_usage() -> None:
    with SessionLocal() as db:
        request = admitted_request(db)
        observation = asyncio.run(
            execute_external_request(
                db, request_id=request.id, provider=FakeProvider(), now=NOW
            )
        )

        stored_request = db.get(ExternalIntelligenceRequest, request.id)
        usage = db.query(ExternalUsageRecord).filter_by(request_id=request.id).one()
        assert stored_request is not None and stored_request.status == "succeeded"
        assert stored_request.actual_cost_micros == 750
        assert usage.actual_cost_micros == 750
        assert observation.normalized_payload["observations"][0]["observed_question"]
        assert observation.source_coverage["cited_sources"] == 1
        assert "fixture" not in str(observation.normalized_payload)


def test_execution_failure_stores_only_generic_status_and_no_partial_records() -> None:
    with SessionLocal() as db:
        request = admitted_request(db)

        with pytest.raises(DataForSeoResponseError):
            asyncio.run(
                execute_external_request(
                    db, request_id=request.id, provider=FakeProvider(fail=True), now=NOW
                )
            )

        stored_request = db.get(ExternalIntelligenceRequest, request.id)
        assert stored_request is not None and stored_request.status == "failed"
        assert stored_request.error_code == "provider_response_invalid"
        assert db.query(ExternalObservation).filter_by(request_id=request.id).count() == 0
        assert db.query(ExternalUsageRecord).filter_by(request_id=request.id).count() == 0


def test_succeeded_request_cannot_be_executed_twice() -> None:
    with SessionLocal() as db:
        request = admitted_request(db)
        provider = FakeProvider()
        asyncio.run(
            execute_external_request(db, request_id=request.id, provider=provider, now=NOW)
        )

        with pytest.raises(ValueError, match="not pending"):
            asyncio.run(
                execute_external_request(db, request_id=request.id, provider=provider, now=NOW)
            )

        assert provider.calls == 1
        assert db.query(ExternalUsageRecord).filter_by(request_id=request.id).count() == 1

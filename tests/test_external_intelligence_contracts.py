import json
from datetime import datetime
from pathlib import Path

import pytest

from app.services.external_intelligence.contracts import (
    AiCitationObservation,
    ExternalQuestionEvidence,
    QuestionEvidenceRequest,
    SerpObservation,
    SourceReference,
    normalized_host,
)
from app.services.external_intelligence.interpretation import assess_external_question_evidence
from app.services.external_intelligence.providers.fake import FakeExternalEvidenceProvider
from app.services.question_coverage import assess_question_coverage

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "external_intelligence" / "nl_question_evidence.json"
)


def load_fixture() -> ExternalQuestionEvidence:
    payload = json.loads(FIXTURE_PATH.read_text())
    request = QuestionEvidenceRequest(**payload["request"])
    serp_payload = payload["serp"]
    serp = SerpObservation(
        provider=serp_payload["provider"],
        observed_at=datetime.fromisoformat(serp_payload["observed_at"]),
        request=request,
        features=tuple(serp_payload["features"]),
        organic_results=tuple(
            SourceReference(**result) for result in serp_payload["organic_results"]
        ),
    )
    citations = tuple(
        AiCitationObservation(
            provider=item["provider"],
            observed_at=datetime.fromisoformat(item["observed_at"]),
            request=request,
            platform=item["platform"],
            answer_excerpt=item["answer_excerpt"],
            sources=tuple(SourceReference(**source) for source in item["sources"]),
        )
        for item in payload["citations"]
    )
    return ExternalQuestionEvidence(
        request=request,
        serp=serp,
        citations=citations,
        source_coverage={"serp": True, "ai_citations": True},
    )


def missing_answer():  # type: ignore[no-untyped-def]
    return assess_question_coverage(
        "wat kosten kunststof kozijnen",
        title="Kunststof kozijnen",
        headings={"h1": ["Kunststof kozijnen"]},
        meta_description=None,
        main_content="Wij leveren isolerende kunststof kozijnen in verschillende kleuren.",
    )


def test_normalized_contract_hides_provider_specific_payloads() -> None:
    evidence = load_fixture()

    assert evidence.request.cache_key == ("wat kosten kunststof kozijnen|nl|NL|mobile|nederland")
    assert evidence.serp is not None
    assert evidence.serp.organic_results[0].domain == "voorbeeld-concurrent.nl"
    assert evidence.citations[0].platform == "google_ai_overview"
    assert not hasattr(evidence, "task_id")


def test_fake_provider_returns_fixture_without_network() -> None:
    evidence = load_fixture()
    provider = FakeExternalEvidenceProvider(
        serp={evidence.request.cache_key: evidence.serp},
        citations={evidence.request.cache_key: evidence.citations},
    )

    assert provider.fetch_serp(evidence.request) == evidence.serp
    assert provider.fetch_citations(evidence.request) == evidence.citations
    assert provider.calls == [
        ("serp", evidence.request.cache_key),
        ("citations", evidence.request.cache_key),
    ]


def test_question_context_mismatch_is_rejected() -> None:
    evidence = load_fixture()
    other = QuestionEvidenceRequest(
        question="hoe lang gaan kunststof kozijnen mee",
        language="nl",
        country="NL",
        device="mobile",
        location="Nederland",
    )

    with pytest.raises(ValueError, match="same question context"):
        ExternalQuestionEvidence(
            request=other,
            serp=evidence.serp,
            citations=evidence.citations,
        )


def test_missing_answer_with_external_sources_becomes_observed_gap() -> None:
    evidence = load_fixture()

    assessment = assess_external_question_evidence(
        page_url="https://eigen-site.nl/kunststof-kozijnen",
        coverage=missing_answer(),
        external=evidence,
    )

    assert assessment.status == "observed_citation_gap"
    assert assessment.confidence == "low"
    assert "voorbeeld-concurrent.nl" in assessment.summary
    assert assessment.recommended_action is not None


def test_own_citation_is_observation_not_quality_claim() -> None:
    evidence = load_fixture()
    own_source = SourceReference(url="https://eigen-site.nl/kunststof-kozijnen")
    own_citation = AiCitationObservation(
        provider="fixture",
        observed_at=evidence.citations[0].observed_at,
        request=evidence.request,
        platform="google_ai_overview",
        sources=(own_source,),
    )
    external = ExternalQuestionEvidence(request=evidence.request, citations=(own_citation,))

    assessment = assess_external_question_evidence(
        page_url="https://www.eigen-site.nl/kunststof-kozijnen",
        coverage=missing_answer(),
        external=external,
    )

    assert normalized_host(own_source.url) == "eigen-site.nl"
    assert assessment.status == "own_page_cited"
    assert assessment.recommended_action is None


def test_empty_observation_never_creates_a_gap() -> None:
    evidence = load_fixture()
    empty = ExternalQuestionEvidence(request=evidence.request)

    assessment = assess_external_question_evidence(
        page_url="https://eigen-site.nl/kunststof-kozijnen",
        coverage=missing_answer(),
        external=empty,
    )

    assert assessment.status == "insufficient_external_evidence"
    assert assessment.recommended_action is None

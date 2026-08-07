from dataclasses import dataclass
from typing import Literal

from app.services.external_intelligence.contracts import ExternalQuestionEvidence, normalized_host
from app.services.question_coverage import QuestionCoverageResult

ExternalAssessmentStatus = Literal[
    "insufficient_external_evidence",
    "own_page_cited",
    "observed_citation_gap",
    "external_context_available",
]


@dataclass(frozen=True)
class ExternalQuestionAssessment:
    status: ExternalAssessmentStatus
    confidence: str
    summary: str
    evidence: tuple[dict[str, object], ...]
    recommended_action: str | None


def assess_external_question_evidence(
    *,
    page_url: str,
    coverage: QuestionCoverageResult,
    external: ExternalQuestionEvidence,
) -> ExternalQuestionAssessment:
    """Interpret bounded observations without treating one AI answer as a market-wide fact."""
    own_host = normalized_host(page_url)
    citation_sources = [source for item in external.citations for source in item.sources]
    citation_hosts = {source.domain for source in citation_sources if source.domain}
    serp_hosts = {
        source.domain
        for source in (external.serp.organic_results if external.serp else ())
        if source.domain
    }
    evidence = (
        {
            "source": "external_observation",
            "question": external.request.question,
            "citation_platforms": sorted({item.platform for item in external.citations}),
            "citation_domains": sorted(citation_hosts),
            "serp_domains": sorted(serp_hosts),
            "warnings": sorted(
                {warning for item in external.citations for warning in item.warnings}
                | set(external.serp.warnings if external.serp else ())
            ),
        },
    )
    if not citation_sources and not (external.serp and external.serp.organic_results):
        return ExternalQuestionAssessment(
            status="insufficient_external_evidence",
            confidence="low",
            summary="Er is nog onvoldoende externe evidence voor deze vraag.",
            evidence=evidence,
            recommended_action=None,
        )
    if own_host in citation_hosts:
        return ExternalQuestionAssessment(
            status="own_page_cited",
            confidence="medium",
            summary="De eigen website is in ten minste één gemeten AI-antwoord als bron gebruikt.",
            evidence=evidence,
            recommended_action=None,
        )
    if citation_sources and coverage.status in {"missing", "partial", "implicit"}:
        cited_examples = ", ".join(sorted(citation_hosts)[:3])
        return ExternalQuestionAssessment(
            status="observed_citation_gap",
            confidence="medium" if len(external.citations) > 1 else "low",
            summary=(
                "De pagina beantwoordt deze relevante vraag nog niet aantoonbaar volledig, terwijl "
                f"de gemeten AI-antwoorden bronnen zoals {cited_examples} gebruiken."
            ),
            evidence=evidence,
            recommended_action=coverage.recommended_action,
        )
    return ExternalQuestionAssessment(
        status="external_context_available",
        confidence="low",
        summary=(
            "Er is externe context beschikbaar, maar één meetset bewijst geen contentprobleem of "
            "citation opportunity."
        ),
        evidence=evidence,
        recommended_action=None,
    )


def assess_stored_citation_evidence(
    *,
    page_url: str,
    coverage: QuestionCoverageResult,
    question: str,
    citation_urls: tuple[str, ...],
    observation_count: int,
) -> ExternalQuestionAssessment:
    """Interpret stored citations without reconstructing provider-specific observations."""
    own_host = normalized_host(page_url)
    citation_hosts = {normalized_host(url) for url in citation_urls if normalized_host(url)}
    evidence = (
        {
            "source": "external_observation",
            "question": question,
            "citation_domains": sorted(citation_hosts),
        },
    )
    if not citation_hosts:
        return ExternalQuestionAssessment(
            status="insufficient_external_evidence",
            confidence="low",
            summary="Bij deze meting zijn geen citeerbare bronnen aangetroffen.",
            evidence=evidence,
            recommended_action=None,
        )
    if own_host in citation_hosts:
        return ExternalQuestionAssessment(
            status="own_page_cited",
            confidence="medium",
            summary="De eigen website is in ten minste één gemeten antwoord als bron gebruikt.",
            evidence=evidence,
            recommended_action=None,
        )
    if coverage.status in {"missing", "partial", "implicit"}:
        return ExternalQuestionAssessment(
            status="observed_citation_gap",
            confidence="medium" if observation_count > 1 else "low",
            summary=(
                "De pagina beantwoordt deze vraag nog niet aantoonbaar volledig, terwijl andere "
                "bronnen bij deze meting wel zijn gebruikt."
            ),
            evidence=evidence,
            recommended_action=coverage.recommended_action,
        )
    return ExternalQuestionAssessment(
        status="external_context_available",
        confidence="low",
        summary=(
            "De pagina beantwoordt de vraag aantoonbaar. Deze ene meting geeft geen reden om de "
            "inhoud alleen voor citations aan te passen."
        ),
        evidence=evidence,
        recommended_action=None,
    )

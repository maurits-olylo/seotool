from typing import Any

from app.services.external_intelligence.contracts import ExternalQuestionEvidence


def public_evidence_payload(evidence: ExternalQuestionEvidence) -> dict[str, Any]:
    """Build user-facing evidence without provider identity, cost or task metadata."""
    serp = evidence.serp
    return {
        "question": evidence.request.question,
        "serp": (
            {
                "observed_at": serp.observed_at.isoformat(),
                "organic_results": [
                    {
                        "url": result.url,
                        "title": result.title,
                        "position": result.position,
                    }
                    for result in serp.organic_results
                ],
                "features": list(serp.features),
                "warnings": list(serp.warnings),
            }
            if serp
            else None
        ),
        "ai_observations": [
            {
                "observed_at": observation.observed_at.isoformat(),
                "observed_question": observation.observed_question,
                "sources": [
                    {
                        "url": source.url,
                        "title": source.title,
                        "position": source.position,
                    }
                    for source in observation.sources
                ],
                "answer_excerpt": observation.answer_excerpt,
                "warnings": list(observation.warnings),
            }
            for observation in evidence.citations
        ],
        "source_coverage": evidence.source_coverage,
    }

from typing import Any

from app.models.external_intelligence import ExternalObservation
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


def public_stored_ai_evidence(
    observation: ExternalObservation, *, question: str
) -> dict[str, Any]:
    """Expose stored AI evidence without provider, cost, answer text or task metadata."""
    raw_observations = observation.normalized_payload.get("observations", [])
    items: list[dict[str, object]] = []
    if isinstance(raw_observations, list):
        for item in raw_observations[:20]:
            if not isinstance(item, dict):
                continue
            raw_sources = item.get("sources", [])
            sources = []
            if isinstance(raw_sources, list):
                sources = [
                    {
                        "url": source.get("url"),
                        "title": source.get("title"),
                        "position": source.get("position"),
                    }
                    for source in raw_sources[:20]
                    if isinstance(source, dict) and isinstance(source.get("url"), str)
                ]
            items.append(
                {
                    "observed_at": item.get("observed_at") or observation.observed_at,
                    "observed_question": item.get("observed_question"),
                    "sources": sources,
                }
            )
    return {
        "observation_id": observation.id,
        "capability": "ai_citations",
        "question": question,
        "observed_at": observation.observed_at,
        "observations": items,
    }

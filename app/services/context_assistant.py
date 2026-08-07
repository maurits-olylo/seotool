from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.discovery import Url
from app.models.issues import Issue, IssueOccurrence
from app.models.opportunities import OpportunityEvaluation
from app.services.issue_guidance import build_issue_guidance

OUT_OF_SCOPE_MARKERS = {
    "concurrent",
    "semrush",
    "ahrefs",
    "moz",
    "andere tool",
    "beste seo tool",
    "marktvergelijking",
}


class ContextAssistantError(ValueError):
    pass


def answer_context_question(
    db: Session,
    *,
    website_id: UUID,
    context_type: str,
    context_id: UUID,
    question: str,
) -> dict[str, object]:
    if any(marker in question.casefold() for marker in OUT_OF_SCOPE_MARKERS):
        return _scope_limited_answer()
    if context_type == "issue":
        return _answer_issue(db, website_id=website_id, issue_id=context_id)
    if context_type == "opportunity_evaluation":
        return _answer_opportunity(db, website_id=website_id, evaluation_id=context_id)
    raise ContextAssistantError("Dit contexttype wordt niet ondersteund.")


def _answer_issue(db: Session, *, website_id: UUID, issue_id: UUID) -> dict[str, object]:
    issue = db.get(Issue, issue_id)
    if issue is None or issue.website_id != website_id:
        raise ContextAssistantError("Contextrecord niet gevonden.")
    occurrence = db.scalar(
        select(IssueOccurrence)
        .where(IssueOccurrence.issue_id == issue.id)
        .order_by(desc(IssueOccurrence.detected_at))
        .limit(1)
    )
    url = db.get(Url, issue.url_id) if issue.url_id else None
    evidence = occurrence.evidence if occurrence else {}
    guidance = build_issue_guidance(issue, evidence)
    facts = [
        f"Signaal: {issue.title}",
        f"Status: {issue.status}; ernst: {issue.severity}; confidence: {issue.confidence}.",
        f"Laatst gedetecteerd: {issue.last_detected_at.isoformat()}.",
    ]
    if url:
        facts.append(f"Betrokken URL: {url.normalized_url}")
    interpretations = [str(guidance["relevance"]["text"])]
    likely_cause = guidance.get("likely_cause")
    if isinstance(likely_cause, dict) and likely_cause.get("text"):
        interpretations.append(f"Waarschijnlijke verklaring: {likely_cause['text']}")
    missing = (
        []
        if occurrence
        else ["Er is geen afzonderlijk meetrecord met technisch bewijs beschikbaar."]
    )
    answer = (
        f"SEO Monitor heeft ‘{issue.title}’ gemeten met confidence {issue.confidence}. "
        f"Aanbevolen vervolgstap: {issue.recommended_action} "
        f"Controle: {guidance['verification']}"
    )
    sources = [
        {
            "source_type": "issue",
            "record_id": issue.id,
            "measured_at": issue.last_detected_at,
            "description": "Actueel issue en lifecycle-status",
        }
    ]
    if occurrence:
        sources.append(
            {
                "source_type": "issue_occurrence",
                "record_id": occurrence.id,
                "measured_at": occurrence.detected_at,
                "description": "Nieuwste opgeslagen waarneming",
            }
        )
    return {
        "status": "answered" if occurrence else "insufficient_evidence",
        "answer": answer,
        "facts": facts,
        "interpretations": interpretations,
        "missing_evidence": missing,
        "confidence": issue.confidence if occurrence else "low",
        "sources": sources,
        "mutations_performed": False,
    }


def _answer_opportunity(db: Session, *, website_id: UUID, evaluation_id: UUID) -> dict[str, object]:
    evaluation = db.get(OpportunityEvaluation, evaluation_id)
    if evaluation is None or evaluation.website_id != website_id:
        raise ContextAssistantError("Contextrecord niet gevonden.")
    pattern = str(evaluation.source_coverage.get("pattern") or "onbekend patroon")
    score = (
        f"{evaluation.total_score:.1f}/100" if evaluation.total_score is not None else "onbekend"
    )
    facts = [
        f"Patroon: {pattern}",
        f"Kansscore: {score}; prioriteitsklasse: {evaluation.priority_class}.",
        (
            f"Meetperiode: {evaluation.period_start.isoformat()} tot "
            f"{evaluation.period_end.isoformat()}."
        ),
        f"Formuleversie: {evaluation.formula_version}.",
    ]
    missing = [
        f"Bron {name} ontbreekt en is niet als nul meegerekend."
        for name, available in evaluation.source_coverage.items()
        if name != "pattern" and available is False
    ]
    dimensions = {
        "potentieel": evaluation.potential_score,
        "frictie": evaluation.friction_score,
        "bewijs": evaluation.evidence_score,
        "uitvoerbaarheid": evaluation.feasibility_score,
    }
    missing.extend(
        f"De deelscore {name} is onbekend." for name, value in dimensions.items() if value is None
    )
    interpretation = (
        "Dit is een uitlegbare prioritering van opgeslagen signalen, geen voorspelling van extra "
        "verkeer en geen algemene SEO-score."
    )
    return {
        "status": "answered" if evaluation.total_score is not None else "insufficient_evidence",
        "answer": (
            f"Deze {pattern}-beoordeling heeft een kansscore van {score}. "
            f"De uitkomst is geclassificeerd als {evaluation.priority_class}; "
            "controleer de bijdragers en ontbrekende bronnen vóór uitvoering."
        ),
        "facts": facts,
        "interpretations": [interpretation],
        "missing_evidence": missing,
        "confidence": _opportunity_confidence(evaluation.evidence_score),
        "sources": [
            {
                "source_type": "opportunity_evaluation",
                "record_id": evaluation.id,
                "measured_at": evaluation.created_at,
                "description": "Historische kansbeoordeling met formule- en brondekking",
            }
        ],
        "mutations_performed": False,
    }


def _opportunity_confidence(evidence_score: float | None) -> str:
    if evidence_score is None or evidence_score < 40:
        return "low"
    if evidence_score < 70:
        return "medium"
    return "high"


def _scope_limited_answer() -> dict[str, object]:
    return {
        "status": "scope_limited",
        "answer": (
            "Ik beantwoord alleen vragen over het zichtbare klantrecord en de betekenis daarvan "
            "binnen SEO Monitor. Marktvergelijkingen, concurrenten en externe tools vallen buiten "
            "deze assistent."
        ),
        "facts": [],
        "interpretations": [],
        "missing_evidence": ["De gevraagde informatie behoort niet tot de zichtbare klantcontext."],
        "confidence": "not_applicable",
        "sources": [],
        "mutations_performed": False,
    }

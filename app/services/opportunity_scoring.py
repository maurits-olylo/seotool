import hashlib
import json
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.opportunities import OpportunityEvaluation

FORMULA_VERSION = "opportunity-score-2026-08-07-v1"
SCORE_WEIGHTS = {
    "potential": 0.40,
    "friction": 0.25,
    "evidence": 0.20,
    "feasibility": 0.15,
}


@dataclass(frozen=True)
class OpportunityScores:
    potential: float | None
    friction: float | None
    evidence: float | None
    feasibility: float | None
    total: float | None
    priority_class: str


def _validated_score(value: float | None) -> float | None:
    if value is None:
        return None
    score = round(float(value), 2)
    if not 0 <= score <= 100:
        raise ValueError("Opportunity scores must be between zero and one hundred")
    return score


def calculate_opportunity_scores(
    *,
    potential: float | None,
    friction: float | None,
    evidence: float | None,
    feasibility: float | None,
) -> OpportunityScores:
    values = {
        "potential": _validated_score(potential),
        "friction": _validated_score(friction),
        "evidence": _validated_score(evidence),
        "feasibility": _validated_score(feasibility),
    }
    if any(value is None for value in values.values()):
        return OpportunityScores(**values, total=None, priority_class="insufficient_evidence")

    complete = {key: float(value) for key, value in values.items() if value is not None}
    total = round(sum(complete[key] * SCORE_WEIGHTS[key] for key in SCORE_WEIGHTS), 2)
    evidence_score = complete["evidence"]
    if evidence_score < 40:
        total = min(total, 39.99)
    elif evidence_score < 60:
        total = min(total, 59.99)

    if evidence_score < 40:
        priority = "insufficient_evidence"
    elif total >= 75:
        priority = "high_opportunity"
    elif total >= 55:
        priority = "opportunity"
    elif total >= 35:
        priority = "monitor"
    else:
        priority = "insufficient_evidence"
    return OpportunityScores(**values, total=total, priority_class=priority)


def opportunity_input_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def store_opportunity_evaluation(
    db: Session,
    *,
    website_id: UUID,
    scope_type: str,
    scope_key: str,
    period_start: date,
    period_end: date,
    scores: OpportunityScores,
    source_coverage: dict[str, object],
    contributors: list[dict[str, object]],
    evidence: list[dict[str, object]],
    primary_url_id: UUID | None = None,
    formula_version: str = FORMULA_VERSION,
) -> tuple[OpportunityEvaluation, bool]:
    if period_start > period_end:
        raise ValueError("Opportunity period start must not be after period end")
    if scope_type not in {"page", "url_family", "shared_cause"}:
        raise ValueError("Unsupported opportunity scope type")
    normalized_input = {
        "scope_type": scope_type,
        "scope_key": scope_key,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "scores": scores.__dict__,
        "source_coverage": source_coverage,
        "contributors": contributors,
        "evidence": evidence,
        "primary_url_id": str(primary_url_id) if primary_url_id else None,
    }
    input_hash = opportunity_input_hash(normalized_input)
    existing = db.scalar(
        select(OpportunityEvaluation).where(
            OpportunityEvaluation.website_id == website_id,
            OpportunityEvaluation.scope_type == scope_type,
            OpportunityEvaluation.scope_key == scope_key,
            OpportunityEvaluation.input_hash == input_hash,
            OpportunityEvaluation.formula_version == formula_version,
        )
    )
    if existing:
        return existing, False
    evaluation = OpportunityEvaluation(
        website_id=website_id,
        primary_url_id=primary_url_id,
        scope_type=scope_type,
        scope_key=scope_key,
        period_start=period_start,
        period_end=period_end,
        input_hash=input_hash,
        formula_version=formula_version,
        potential_score=scores.potential,
        friction_score=scores.friction,
        evidence_score=scores.evidence,
        feasibility_score=scores.feasibility,
        total_score=scores.total,
        priority_class=scores.priority_class,
        source_coverage=source_coverage,
        contributors=contributors,
        evidence=evidence,
    )
    db.add(evaluation)
    db.flush()
    return evaluation, True

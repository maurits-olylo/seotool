from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class OpportunityEvaluationRead(BaseModel):
    id: UUID
    website_id: UUID
    primary_url_id: UUID | None
    scope_type: str
    scope_key: str
    period_start: date
    period_end: date
    formula_version: str
    potential_score: float | None
    friction_score: float | None
    evidence_score: float | None
    feasibility_score: float | None
    total_score: float | None
    priority_class: str
    source_coverage: dict[str, object]
    contributors: list[dict[str, object]]
    evidence: list[dict[str, object]]
    created_at: datetime

    model_config = {"from_attributes": True}

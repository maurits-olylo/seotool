from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class EffectEvaluationRead(BaseModel):
    id: UUID
    website_id: UUID
    change_period_start: date
    change_period_end: date
    baseline_start: date
    baseline_end: date
    observation_start: date
    observation_end: date
    method_version: str
    status: str
    analytics_source: str | None
    intervention_ids: list[str]
    url_ids: list[str]
    metrics: dict[str, object]
    source_coverage: dict[str, object]
    confidence_factors: dict[str, object]
    evidence: list[dict[str, object]]
    created_at: datetime

    model_config = {"from_attributes": True}


class EffectInterventionRegistrationRead(BaseModel):
    id: UUID
    task_id: UUID
    created: bool

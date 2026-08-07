from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ContextAssistantQuestion(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    context_type: Literal["issue", "opportunity_evaluation", "website_performance"]
    context_id: UUID
    period_end: date | None = None
    days: int = Field(default=28, ge=28, le=90)

    @model_validator(mode="after")
    def require_performance_period(self) -> "ContextAssistantQuestion":
        if self.context_type == "website_performance" and self.period_end is None:
            raise ValueError("period_end is required for website performance context")
        return self


class ContextSourceReference(BaseModel):
    source_type: str
    record_id: UUID
    measured_at: datetime | None = None
    description: str


class ContextAssistantAnswer(BaseModel):
    status: Literal["answered", "scope_limited", "insufficient_evidence"]
    answer: str
    facts: list[str]
    interpretations: list[str]
    missing_evidence: list[str]
    confidence: str
    sources: list[ContextSourceReference]
    mutations_performed: bool = False

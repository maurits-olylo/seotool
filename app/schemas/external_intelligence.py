from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ExternalEvidenceCreate(BaseModel):
    capability: Literal["serp", "ai_citations"]
    question: str = Field(min_length=1, max_length=250)
    language: str = Field(min_length=2, max_length=2)
    country: str = Field(min_length=2, max_length=2)
    device: Literal["desktop", "mobile"]
    location: str | None = Field(default=None, min_length=1, max_length=120)
    url_id: UUID | None = None


class ExternalEvidenceState(BaseModel):
    request_id: UUID | None = None
    observation_id: UUID | None = None
    status: Literal[
        "queued",
        "pending",
        "running",
        "available",
        "failed",
        "cancelled",
        "budget_exceeded",
        "scope_limit_reached",
    ]
    capability: Literal["serp", "ai_citations"]


class ExternalEvidenceControlsUpdate(BaseModel):
    enabled: bool
    monthly_check_limit: int = Field(ge=0, le=1000)
    active_question_limit: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_enabled_limits(self) -> "ExternalEvidenceControlsUpdate":
        if self.enabled and (
            self.monthly_check_limit < 1 or self.active_question_limit < 1
        ):
            raise ValueError("Enabled controls require positive limits")
        return self


class ExternalEvidenceControlsRead(ExternalEvidenceControlsUpdate):
    available: bool
    checks_completed_this_month: int
    checks_in_progress: int
    active_questions: int


class ExternalEvidenceSource(BaseModel):
    url: str
    title: str | None = None
    position: int | None = None


class ExternalAiObservation(BaseModel):
    observed_at: datetime
    observed_question: str | None = None
    sources: list[ExternalEvidenceSource]


class ExternalEvidenceAssessment(BaseModel):
    status: Literal[
        "insufficient_external_evidence",
        "own_page_cited",
        "observed_citation_gap",
        "external_context_available",
    ]
    confidence: Literal["low", "medium", "high"]
    coverage_status: Literal["answered", "partial", "implicit", "missing"]
    summary: str
    recommended_action: str | None = None


class ExternalEvidenceResult(BaseModel):
    observation_id: UUID
    capability: Literal["ai_citations"]
    question: str
    observed_at: datetime
    observations: list[ExternalAiObservation]
    assessment: ExternalEvidenceAssessment | None = None

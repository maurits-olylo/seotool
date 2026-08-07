from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


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

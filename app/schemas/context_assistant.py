from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ContextAssistantQuestion(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    context_type: Literal["issue", "opportunity_evaluation"]
    context_id: UUID


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

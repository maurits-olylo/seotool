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

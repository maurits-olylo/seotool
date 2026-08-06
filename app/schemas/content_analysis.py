from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.content_classification import normalize_branded_terms

SearchIntent = Literal[
    "informational", "commercial", "transactional", "trust", "navigational", "mixed", "uncertain"
]
JourneyStage = Literal[
    "discover", "understand", "consider", "compare", "decide", "act", "aftercare", "uncertain"
]
ContentRole = Literal[
    "attract",
    "support_choice",
    "provide_proof",
    "convert",
    "navigate",
    "support_customers",
    "uncertain",
]


class ContentAnalysisSettingsData(BaseModel):
    website_id: UUID | None = None
    branded_terms: list[str] = Field(default_factory=list, max_length=100)
    sector_template: str | None = Field(default=None, max_length=80)

    model_config = {"from_attributes": True}

    @field_validator("branded_terms")
    @classmethod
    def clean_branded_terms(cls, value: list[str]) -> list[str]:
        terms = normalize_branded_terms(value)
        if any(len(term) > 100 for term in terms):
            raise ValueError("Branded terms may contain at most 100 characters")
        return terms


class ContentOverrideWrite(BaseModel):
    search_intent: SearchIntent | None = None
    journey_stage: JourneyStage | None = None
    content_role: ContentRole | None = None
    is_locked: bool = True
    rationale: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_selection(self) -> "ContentOverrideWrite":
        if not any((self.search_intent, self.journey_stage, self.content_role)):
            raise ValueError("Select at least one classification value")
        return self


class ContentOverrideRead(ContentOverrideWrite):
    id: UUID
    website_id: UUID
    url_id: UUID
    updated_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

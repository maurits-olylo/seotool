from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel

IssueStatus = Literal[
    "new",
    "review",
    "accepted",
    "planned",
    "in_progress",
    "waiting_for_client",
    "resolved",
    "verified",
    "ignored",
    "accepted_risk",
]


class ChangeRead(ORMModel):
    id: UUID
    website_id: UUID
    url_id: UUID
    previous_snapshot_id: UUID | None
    current_snapshot_id: UUID
    change_type: str
    field_name: str | None
    old_value: str | None
    new_value: str | None
    detected_at: datetime
    is_baseline: bool = False
    previous_checked_at: datetime | None = None
    current_checked_at: datetime | None = None
    importance: str = "low"
    relevance: str = "Controleer of deze wijziging bewust is."
    review_action: str = "Vergelijk de pagina met de vorige versie."


class ChangeDetailRead(ChangeRead):
    details: dict[str, object]


class IssueRead(ORMModel):
    id: UUID
    website_id: UUID
    url_id: UUID | None
    issue_type: str
    category: str
    severity: str
    confidence: str
    status: str
    title: str
    description: str
    recommended_action: str
    first_detected_at: datetime
    last_detected_at: datetime
    resolved_at: datetime | None
    verified_at: datetime | None
    assigned_to: str | None
    due_date: date | None
    organic_impact: dict[str, object] | None = None


class ElementLocationRead(BaseModel):
    id: UUID
    source_url: str
    issue_type: str
    element_type: str
    target_url: str | None
    visible_text: str | None
    element_id: str | None
    css_selector: str | None
    xpath: str | None
    html_fragment: str
    occurrence_index: int
    text_prefix: str | None
    text_suffix: str | None
    jump_url: str | None


class GuidanceStatementRead(BaseModel):
    text: str
    basis: Literal["fact", "interpretation", "hypothesis"]


class IssueGuidanceRead(BaseModel):
    relevance: GuidanceStatementRead
    likely_cause: GuidanceStatementRead | None
    alternative_explanation: GuidanceStatementRead | None
    steps: list[str]
    verification: str
    confidence: str


class IssueDetailRead(IssueRead):
    evidence: dict[str, object]
    source_urls: list[str]
    elements: list[ElementLocationRead]
    guidance: IssueGuidanceRead


class IssueUpdate(BaseModel):
    status: IssueStatus | None = None
    assigned_to: str | None = None
    due_date: date | None = None


class IssueBulkAction(BaseModel):
    issue_ids: list[UUID] = Field(min_length=1, max_length=1000)
    action: Literal["resolve_and_recheck", "suppress_issue_type"]
    comment: str | None = Field(default=None, max_length=2000)


class IssueBulkResult(BaseModel):
    action: str
    updated_count: int
    suppression_count: int = 0


class IssueSuppressionRead(ORMModel):
    id: UUID
    website_id: UUID
    url_id: UUID
    issue_type: str
    actor: str | None
    comment: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    restored_at: datetime | None
    restored_by: str | None


class CommentCreate(BaseModel):
    author: str
    comment: str


class CommentRead(ORMModel):
    id: UUID
    issue_id: UUID
    author: str
    comment: str
    created_at: datetime

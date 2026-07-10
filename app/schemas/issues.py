from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

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


class IssueUpdate(BaseModel):
    status: IssueStatus | None = None
    assigned_to: str | None = None
    due_date: date | None = None


class CommentCreate(BaseModel):
    author: str
    comment: str


class CommentRead(ORMModel):
    id: UUID
    issue_id: UUID
    author: str
    comment: str
    created_at: datetime

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel, Timestamped

TaskStatus = Literal[
    "open",
    "planned",
    "in_progress",
    "waiting_for_input",
    "implemented",
    "closed",
]
CloseReason = Literal[
    "verified",
    "manually_accepted",
    "rejected",
    "superseded",
    "no_longer_relevant",
]
TaskRole = Literal["content", "development", "seo_analytics", "project_management"]
TaskPriority = Literal["critical", "high", "normal", "low"]


class RecommendationDefinitionRead(BaseModel):
    key: str
    version: str
    source_issue_types: frozenset[str]
    title: str
    primary_role: TaskRole
    supporting_roles: tuple[TaskRole, ...]
    default_priority: TaskPriority
    effort_minutes: tuple[int, int] | None
    feasibility: str
    steps: tuple[str, ...]
    completion_criteria: tuple[str, ...]
    verification_scope: tuple[str, ...]


class RecommendationTaskRead(Timestamped):
    website_id: UUID
    created_by_user_id: UUID | None
    assigned_to_user_id: UUID | None
    primary_issue_id: UUID | None
    recommendation_type: str
    definition_version: str
    title: str
    category: str
    status: TaskStatus
    close_reason: CloseReason | None
    primary_role: TaskRole
    supporting_roles: list[TaskRole]
    priority: TaskPriority
    priority_reason: str
    effort_min_minutes: int | None
    effort_max_minutes: int | None
    effort_confidence: str
    feasibility: str
    action: str
    rationale: str
    steps: list[str]
    dependencies: list[str]
    required_input: list[str]
    acceptance_criteria: list[str]
    verification_spec: dict[str, object]
    verification_status: str
    implemented_at: datetime | None
    closed_at: datetime | None


class RecommendationTaskUrlRead(ORMModel):
    id: UUID
    url_id: UUID
    role: str
    is_user_supplied: bool


class RecommendationTaskEventRead(ORMModel):
    id: UUID
    actor_user_id: UUID | None
    actor_label: str | None
    event_type: str
    previous_status: str | None
    new_status: str | None
    comment: str | None
    details: dict[str, object]
    occurred_at: datetime


class RecommendationTaskDetailRead(RecommendationTaskRead):
    issue_ids: list[UUID]
    urls: list[RecommendationTaskUrlRead]
    events: list[RecommendationTaskEventRead]


class RecommendationTaskUpdate(BaseModel):
    status: TaskStatus | None = None
    close_reason: CloseReason | None = None
    assigned_to_user_id: UUID | None = None
    primary_role: TaskRole | None = None
    priority: TaskPriority | None = None
    priority_reason: str | None = Field(default=None, min_length=1, max_length=2000)
    effort_min_minutes: int | None = Field(default=None, ge=0)
    effort_max_minutes: int | None = Field(default=None, ge=0)
    comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_close_reason(self) -> "RecommendationTaskUpdate":
        if self.status == "closed" and self.close_reason is None:
            raise ValueError("close_reason is required when closing a task")
        if self.close_reason is not None and self.status != "closed":
            raise ValueError("close_reason is only allowed when closing a task")
        if (
            self.effort_min_minutes is not None
            and self.effort_max_minutes is not None
            and self.effort_max_minutes < self.effort_min_minutes
        ):
            raise ValueError("effort_max_minutes must be greater than or equal to minimum")
        return self

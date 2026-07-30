import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import UUIDTimestampMixin, utc_now

TASK_STATUSES = ("open", "planned", "in_progress", "waiting_for_input", "implemented", "closed")
CLOSE_REASONS = ("verified", "manually_accepted", "rejected", "superseded", "no_longer_relevant")
TASK_ROLES = ("content", "development", "seo_analytics", "project_management")
TASK_PRIORITIES = ("critical", "high", "normal", "low")
VERIFICATION_STATUSES = (
    "not_requested",
    "queued",
    "running",
    "passed",
    "likely_passed",
    "manual_review",
    "failed",
    "error",
    "cancelled",
)


def _values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class RecommendationTask(UUIDTimestampMixin, Base):
    __tablename__ = "recommendation_tasks"
    __table_args__ = (
        CheckConstraint(f"status IN ({_values(TASK_STATUSES)})", name="ck_task_status"),
        CheckConstraint(
            f"close_reason IS NULL OR close_reason IN ({_values(CLOSE_REASONS)})",
            name="ck_task_close_reason",
        ),
        CheckConstraint(f"primary_role IN ({_values(TASK_ROLES)})", name="ck_task_primary_role"),
        CheckConstraint(f"priority IN ({_values(TASK_PRIORITIES)})", name="ck_task_priority"),
        CheckConstraint(
            f"verification_status IN ({_values(VERIFICATION_STATUSES)})",
            name="ck_task_verification_status",
        ),
        CheckConstraint(
            "effort_min_minutes IS NULL OR effort_min_minutes >= 0",
            name="ck_task_effort_min_nonnegative",
        ),
        CheckConstraint(
            "effort_max_minutes IS NULL OR effort_max_minutes >= effort_min_minutes",
            name="ck_task_effort_range",
        ),
    )

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    primary_issue_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("issues.id", ondelete="SET NULL"), index=True
    )
    recommendation_type: Mapped[str] = mapped_column(String(100), index=True)
    definition_version: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    close_reason: Mapped[str | None] = mapped_column(String(30))
    primary_role: Mapped[str] = mapped_column(String(30), index=True)
    supporting_roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    priority: Mapped[str] = mapped_column(String(20), default="normal", index=True)
    priority_reason: Mapped[str] = mapped_column(Text)
    effort_min_minutes: Mapped[int | None] = mapped_column(Integer)
    effort_max_minutes: Mapped[int | None] = mapped_column(Integer)
    effort_confidence: Mapped[str] = mapped_column(String(20), default="low")
    feasibility: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    steps: Mapped[list[str]] = mapped_column(JSON, default=list)
    dependencies: Mapped[list[str]] = mapped_column(JSON, default=list)
    required_input: Mapped[list[str]] = mapped_column(JSON, default=list)
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSON, default=list)
    verification_spec: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    verification_status: Mapped[str] = mapped_column(
        String(30), default="not_requested", index=True
    )
    implemented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RecommendationTaskIssue(Base):
    __tablename__ = "recommendation_task_issues"

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recommendation_tasks.id", ondelete="CASCADE"), primary_key=True
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True
    )


class RecommendationTaskUrl(Base):
    __tablename__ = "recommendation_task_urls"
    __table_args__ = (UniqueConstraint("task_id", "url_id", "role"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recommendation_tasks.id", ondelete="CASCADE"), index=True
    )
    url_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("urls.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(30), index=True)
    is_user_supplied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RecommendationTaskEvent(Base):
    __tablename__ = "recommendation_task_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recommendation_tasks.id", ondelete="CASCADE"), index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    actor_label: Mapped[str | None] = mapped_column(String(320))
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    previous_status: Mapped[str | None] = mapped_column(String(30))
    new_status: Mapped[str | None] = mapped_column(String(30))
    comment: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class RecommendationFeedback(Base):
    __tablename__ = "recommendation_feedback"
    __table_args__ = (
        CheckConstraint(
            "actual_minutes IS NULL OR actual_minutes >= 0",
            name="ck_recommendation_feedback_actual_minutes",
        ),
        CheckConstraint(
            "actual_effort_band IS NULL OR actual_effort_band IN "
            "('under_15', '15_30', '30_60', '1_2_hours', '2_4_hours', "
            "'4_8_hours', 'more_than_day')",
            name="ck_recommendation_feedback_effort_band",
        ),
        CheckConstraint(
            "difficulty IS NULL OR difficulty IN ('easy', 'expected', 'hard', 'blocked')",
            name="ck_recommendation_feedback_difficulty",
        ),
        CheckConstraint(
            "final_assessment IS NULL OR final_assessment IN "
            "('completed', 'partially_completed', 'not_completed')",
            name="ck_recommendation_feedback_final_assessment",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recommendation_tasks.id", ondelete="CASCADE"), index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    actual_minutes: Mapped[int | None] = mapped_column(Integer)
    actual_effort_band: Mapped[str | None] = mapped_column(String(30))
    difficulty: Mapped[str | None] = mapped_column(String(20))
    instruction_helpful: Mapped[bool | None] = mapped_column(Boolean)
    missing_input: Mapped[bool | None] = mapped_column(Boolean)
    missing_dependency: Mapped[bool | None] = mapped_column(Boolean)
    correction_reason: Mapped[str | None] = mapped_column(String(100))
    rejection_reason: Mapped[str | None] = mapped_column(String(100))
    verification_outcome: Mapped[str | None] = mapped_column(String(30))
    final_assessment: Mapped[str | None] = mapped_column(String(30))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RecommendationVerification(UUIDTimestampMixin, Base):
    __tablename__ = "recommendation_verifications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'passed', 'likely_passed', "
            "'manual_review', 'failed', 'error', 'cancelled')",
            name="ck_recommendation_verification_status",
        ),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recommendation_tasks.id", ondelete="CASCADE"), index=True
    )
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    crawl_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_jobs.id", ondelete="SET NULL"), unique=True, index=True
    )
    verification_type: Mapped[str] = mapped_column(String(100), index=True)
    scope_version: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    scope: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    rules: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    before_snapshot_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    after_snapshot_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    result: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

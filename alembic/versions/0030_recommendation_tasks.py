"""Add recommendation task foundation.

Revision ID: 0030
Revises: 0029
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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


def upgrade() -> None:
    op.create_table(
        "recommendation_tasks",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_to_user_id", sa.Uuid(), nullable=True),
        sa.Column("primary_issue_id", sa.Uuid(), nullable=True),
        sa.Column("recommendation_type", sa.String(length=100), nullable=False),
        sa.Column("definition_version", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="open"),
        sa.Column("close_reason", sa.String(length=30), nullable=True),
        sa.Column("primary_role", sa.String(length=30), nullable=False),
        sa.Column("supporting_roles", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="normal"),
        sa.Column("priority_reason", sa.Text(), nullable=False),
        sa.Column("effort_min_minutes", sa.Integer(), nullable=True),
        sa.Column("effort_max_minutes", sa.Integer(), nullable=True),
        sa.Column("effort_confidence", sa.String(length=20), nullable=False, server_default="low"),
        sa.Column("feasibility", sa.String(length=40), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("dependencies", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("required_input", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("acceptance_criteria", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("verification_spec", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "verification_status",
            sa.String(length=30),
            nullable=False,
            server_default="not_requested",
        ),
        sa.Column("implemented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"status IN ({_values(TASK_STATUSES)})", name="ck_task_status"),
        sa.CheckConstraint(
            f"close_reason IS NULL OR close_reason IN ({_values(CLOSE_REASONS)})",
            name="ck_task_close_reason",
        ),
        sa.CheckConstraint(
            f"primary_role IN ({_values(TASK_ROLES)})",
            name="ck_task_primary_role",
        ),
        sa.CheckConstraint(
            f"priority IN ({_values(TASK_PRIORITIES)})",
            name="ck_task_priority",
        ),
        sa.CheckConstraint(
            f"verification_status IN ({_values(VERIFICATION_STATUSES)})",
            name="ck_task_verification_status",
        ),
        sa.CheckConstraint(
            "effort_min_minutes IS NULL OR effort_min_minutes >= 0",
            name="ck_task_effort_min_nonnegative",
        ),
        sa.CheckConstraint(
            "effort_max_minutes IS NULL OR effort_max_minutes >= effort_min_minutes",
            name="ck_task_effort_range",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["primary_issue_id"], ["issues.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, column in (
        ("ix_recommendation_tasks_website_id", "website_id"),
        ("ix_recommendation_tasks_created_by_user_id", "created_by_user_id"),
        ("ix_recommendation_tasks_assigned_to_user_id", "assigned_to_user_id"),
        ("ix_recommendation_tasks_primary_issue_id", "primary_issue_id"),
        ("ix_recommendation_tasks_recommendation_type", "recommendation_type"),
        ("ix_recommendation_tasks_category", "category"),
        ("ix_recommendation_tasks_status", "status"),
        ("ix_recommendation_tasks_primary_role", "primary_role"),
        ("ix_recommendation_tasks_priority", "priority"),
        ("ix_recommendation_tasks_verification_status", "verification_status"),
    ):
        op.create_index(name, "recommendation_tasks", [column])

    op.create_table(
        "recommendation_task_issues",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("issue_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["recommendation_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "issue_id"),
    )
    op.create_table(
        "recommendation_task_urls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("url_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("is_user_supplied", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["recommendation_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["url_id"], ["urls.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "url_id", "role"),
    )
    op.create_index("ix_recommendation_task_urls_task_id", "recommendation_task_urls", ["task_id"])
    op.create_index("ix_recommendation_task_urls_url_id", "recommendation_task_urls", ["url_id"])
    op.create_index("ix_recommendation_task_urls_role", "recommendation_task_urls", ["role"])

    op.create_table(
        "recommendation_task_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_label", sa.String(length=320), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("previous_status", sa.String(length=30), nullable=True),
        sa.Column("new_status", sa.String(length=30), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["recommendation_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recommendation_task_events_task_id", "recommendation_task_events", ["task_id"]
    )
    op.create_index(
        "ix_recommendation_task_events_actor_user_id",
        "recommendation_task_events",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_recommendation_task_events_event_type",
        "recommendation_task_events",
        ["event_type"],
    )
    op.create_index(
        "ix_recommendation_task_events_occurred_at",
        "recommendation_task_events",
        ["occurred_at"],
    )

    op.create_table(
        "recommendation_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actual_minutes", sa.Integer(), nullable=True),
        sa.Column("actual_effort_band", sa.String(length=30), nullable=True),
        sa.Column("difficulty", sa.String(length=20), nullable=True),
        sa.Column("instruction_helpful", sa.Boolean(), nullable=True),
        sa.Column("correction_reason", sa.String(length=100), nullable=True),
        sa.Column("rejection_reason", sa.String(length=100), nullable=True),
        sa.Column("verification_outcome", sa.String(length=30), nullable=True),
        sa.Column("final_assessment", sa.String(length=30), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["recommendation_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "actual_minutes IS NULL OR actual_minutes >= 0",
            name="ck_recommendation_feedback_actual_minutes",
        ),
    )
    op.create_index(
        "ix_recommendation_feedback_task_id", "recommendation_feedback", ["task_id"]
    )
    op.create_index(
        "ix_recommendation_feedback_actor_user_id",
        "recommendation_feedback",
        ["actor_user_id"],
    )


def downgrade() -> None:
    op.drop_table("recommendation_feedback")
    op.drop_table("recommendation_task_events")
    op.drop_table("recommendation_task_urls")
    op.drop_table("recommendation_task_issues")
    op.drop_table("recommendation_tasks")

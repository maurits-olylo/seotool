"""Add task notifications and broaden execution roles.

Revision ID: 0042
Revises: 0041
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_ROLES = ("content", "development", "seo_analytics", "project_management")
TASK_ROLES = (
    *OLD_ROLES,
    "content_editor",
    "ux_ui_design",
    "web_development",
    "seo_specialist",
    "analytics_specialist",
    "website_management",
)


def _values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    with op.batch_alter_table("recommendation_tasks") as batch:
        batch.drop_constraint("ck_task_primary_role", type_="check")
        batch.create_check_constraint(
            "ck_task_primary_role",
            f"primary_role IN ({_values(TASK_ROLES)})",
        )
    op.create_table(
        "task_notifications",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("verification_id", sa.Uuid(), nullable=True),
        sa.Column("notification_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["recommendation_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["verification_id"], ["recommendation_verifications.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("website_id", "task_id", "verification_id", "notification_type"):
        op.create_index(f"ix_task_notifications_{column}", "task_notifications", [column])
    op.create_table(
        "task_notification_receipts",
        sa.Column("notification_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["notification_id"], ["task_notifications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("notification_id", "user_id"),
    )


def downgrade() -> None:
    op.drop_table("task_notification_receipts")
    op.drop_table("task_notifications")
    op.execute(
        sa.text(
            """UPDATE recommendation_tasks
            SET primary_role = CASE primary_role
                WHEN 'content_editor' THEN 'content'
                WHEN 'ux_ui_design' THEN 'development'
                WHEN 'web_development' THEN 'development'
                WHEN 'seo_specialist' THEN 'seo_analytics'
                WHEN 'analytics_specialist' THEN 'seo_analytics'
                WHEN 'website_management' THEN 'project_management'
                ELSE primary_role
            END
            WHERE primary_role IN (
                'content_editor', 'ux_ui_design', 'web_development',
                'seo_specialist', 'analytics_specialist', 'website_management'
            )"""
        )
    )
    with op.batch_alter_table("recommendation_tasks") as batch:
        batch.drop_constraint("ck_task_primary_role", type_="check")
        batch.create_check_constraint(
            "ck_task_primary_role",
            f"primary_role IN ({_values(OLD_ROLES)})",
        )

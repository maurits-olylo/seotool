"""Add scoped recommendation verifications.

Revision ID: 0031
Revises: 0030
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recommendation_verifications",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("crawl_job_id", sa.Uuid(), nullable=True),
        sa.Column("verification_type", sa.String(length=100), nullable=False),
        sa.Column("scope_version", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("scope", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("rules", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("before_snapshot_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("after_snapshot_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("result", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'passed', 'likely_passed', "
            "'manual_review', 'failed', 'error', 'cancelled')",
            name="ck_recommendation_verification_status",
        ),
        sa.ForeignKeyConstraint(["crawl_job_id"], ["crawl_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["recommendation_tasks.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("crawl_job_id"),
    )
    for name, column in (
        ("ix_recommendation_verifications_task_id", "task_id"),
        ("ix_recommendation_verifications_requested_by_user_id", "requested_by_user_id"),
        ("ix_recommendation_verifications_crawl_job_id", "crawl_job_id"),
        ("ix_recommendation_verifications_verification_type", "verification_type"),
        ("ix_recommendation_verifications_status", "status"),
    ):
        op.create_index(name, "recommendation_verifications", [column])


def downgrade() -> None:
    op.drop_table("recommendation_verifications")

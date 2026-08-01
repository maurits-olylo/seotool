"""Add durable element-location retention operations.

Revision ID: 0035
Revises: 0034
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "retention_operations",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("trigger_crawl_run_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("rows_deleted", sa.Integer(), nullable=False),
        sa.Column("batches_completed", sa.Integer(), nullable=False),
        sa.Column("candidates_remaining", sa.Integer(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["trigger_crawl_run_id"], ["crawl_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trigger_crawl_run_id"),
    )
    op.create_index(
        op.f("ix_retention_operations_website_id"),
        "retention_operations",
        ["website_id"],
    )
    op.create_index(
        op.f("ix_retention_operations_trigger_crawl_run_id"),
        "retention_operations",
        ["trigger_crawl_run_id"],
    )
    op.create_index(op.f("ix_retention_operations_status"), "retention_operations", ["status"])
    op.create_index(
        op.f("ix_retention_operations_next_attempt_at"),
        "retention_operations",
        ["next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_table("retention_operations")

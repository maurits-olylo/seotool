"""Add bounded PageSpeed and CrUX observations.

Revision ID: 0041
Revises: 0040
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "performance_observations",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("url_id", sa.Uuid(), nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("strategy", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("requested_url", sa.String(length=2048), nullable=False),
        sa.Column("final_url", sa.String(length=2048), nullable=True),
        sa.Column("lighthouse_version", sa.String(length=40), nullable=True),
        sa.Column("fetch_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("category_scores", sa.JSON(), nullable=False),
        sa.Column("lab_metrics", sa.JSON(), nullable=False),
        sa.Column("field_metrics", sa.JSON(), nullable=False),
        sa.Column("origin_field_metrics", sa.JSON(), nullable=False),
        sa.Column("failed_audits", sa.JSON(), nullable=False),
        sa.Column("field_scope", sa.String(length=30), nullable=True),
        sa.Column("collection_period_days", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["url_id"], ["urls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_performance_observations_website_id"),
        "performance_observations",
        ["website_id"],
    )
    op.create_index(
        op.f("ix_performance_observations_url_id"), "performance_observations", ["url_id"]
    )
    op.create_index(
        op.f("ix_performance_observations_analyzed_at"),
        "performance_observations",
        ["analyzed_at"],
    )
    op.create_index(
        op.f("ix_performance_observations_strategy"), "performance_observations", ["strategy"]
    )
    op.create_index(
        op.f("ix_performance_observations_status"), "performance_observations", ["status"]
    )


def downgrade() -> None:
    op.drop_table("performance_observations")

"""Add separate aggregated Matomo metrics.

Revision ID: 0044
Revises: 0043
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "matomo_page_metrics",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("url_id", sa.Uuid(), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("page_url", sa.String(2048), nullable=False),
        sa.Column("visits", sa.Integer(), nullable=False),
        sa.Column("pageviews", sa.Integer(), nullable=False),
        sa.Column("unique_pageviews", sa.Integer(), nullable=False),
        sa.Column("conversions", sa.Float(), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["url_id"], ["urls.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("website_id", "date", "page_url"),
    )
    for column in ("website_id", "url_id", "date"):
        op.create_index(f"ix_matomo_page_metrics_{column}", "matomo_page_metrics", [column])

    op.create_table(
        "matomo_aggregate_metrics",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("metric_type", sa.String(40), nullable=False),
        sa.Column("dimension_key", sa.String(512), nullable=False),
        sa.Column("dimension_name", sa.String(512), nullable=False),
        sa.Column("visits", sa.Integer(), nullable=False),
        sa.Column("actions", sa.Integer(), nullable=False),
        sa.Column("conversions", sa.Float(), nullable=False),
        sa.Column("revenue", sa.Float(), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("website_id", "date", "metric_type", "dimension_key"),
    )
    for column in ("website_id", "date", "metric_type"):
        op.create_index(
            f"ix_matomo_aggregate_metrics_{column}", "matomo_aggregate_metrics", [column]
        )


def downgrade() -> None:
    op.drop_table("matomo_aggregate_metrics")
    op.drop_table("matomo_page_metrics")

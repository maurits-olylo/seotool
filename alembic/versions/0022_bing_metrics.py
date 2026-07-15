"""Store Bing Webmaster page and query metrics.

Revision ID: 0022
Revises: 0021
"""

import sqlalchemy as sa

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bing_page_metrics",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("url_id", sa.Uuid(), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("page_url", sa.String(length=2048), nullable=False),
        sa.Column("clicks", sa.Integer(), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False),
        sa.Column("average_click_position", sa.Float(), nullable=False),
        sa.Column("average_impression_position", sa.Float(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["url_id"], ["urls.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("website_id", "date", "page_url"),
    )
    op.create_index("ix_bing_page_metrics_date", "bing_page_metrics", ["date"])
    op.create_index("ix_bing_page_metrics_url_id", "bing_page_metrics", ["url_id"])
    op.create_index("ix_bing_page_metrics_website_id", "bing_page_metrics", ["website_id"])
    op.create_table(
        "bing_query_metrics",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("query", sa.String(length=2048), nullable=False),
        sa.Column("clicks", sa.Integer(), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False),
        sa.Column("average_click_position", sa.Float(), nullable=False),
        sa.Column("average_impression_position", sa.Float(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("website_id", "date", "query"),
    )
    op.create_index("ix_bing_query_metrics_date", "bing_query_metrics", ["date"])
    op.create_index("ix_bing_query_metrics_website_id", "bing_query_metrics", ["website_id"])


def downgrade() -> None:
    op.drop_table("bing_query_metrics")
    op.drop_table("bing_page_metrics")

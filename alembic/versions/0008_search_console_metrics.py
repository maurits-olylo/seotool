"""Store daily Search Console page metrics."""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"


def upgrade() -> None:
    op.create_table(
        "search_console_metrics",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("url_id", sa.Uuid()),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("page_url", sa.String(2048), nullable=False),
        sa.Column("clicks", sa.Float(), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False),
        sa.Column("ctr", sa.Float(), nullable=False),
        sa.Column("position", sa.Float(), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["url_id"], ["urls.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("website_id", "date", "page_url"),
    )
    op.create_index(
        "ix_search_console_metrics_website_id", "search_console_metrics", ["website_id"]
    )
    op.create_index("ix_search_console_metrics_url_id", "search_console_metrics", ["url_id"])
    op.create_index("ix_search_console_metrics_date", "search_console_metrics", ["date"])


def downgrade() -> None:
    op.drop_table("search_console_metrics")

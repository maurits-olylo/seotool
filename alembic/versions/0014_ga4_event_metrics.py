"""Store daily organic GA4 key events by event name.

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_analytics_event_metrics",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("event_name", sa.String(length=255), nullable=False),
        sa.Column("key_events", sa.Float(), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("website_id", "date", "event_name"),
    )
    op.create_index(
        "ix_google_analytics_event_metrics_website_id",
        "google_analytics_event_metrics",
        ["website_id"],
    )
    op.create_index("ix_google_analytics_event_metrics_date", "google_analytics_event_metrics", ["date"])
    op.create_index(
        "ix_google_analytics_event_metrics_event_name",
        "google_analytics_event_metrics",
        ["event_name"],
    )


def downgrade() -> None:
    op.drop_table("google_analytics_event_metrics")

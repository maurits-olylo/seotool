"""Store qualified GA4 events per organic landing page.

Revision ID: 0019
Revises: 0018
"""

import sqlalchemy as sa

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_analytics_landing_page_event_metrics",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("url_id", sa.Uuid(), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("landing_page", sa.String(length=2048), nullable=False),
        sa.Column("event_name", sa.String(length=255), nullable=False),
        sa.Column("key_events", sa.Float(), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["url_id"], ["urls.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("website_id", "date", "landing_page", "event_name"),
    )
    op.create_index(
        "ix_ga_landing_events_website_id",
        "google_analytics_landing_page_event_metrics",
        ["website_id"],
    )
    op.create_index(
        "ix_ga_landing_events_url_id",
        "google_analytics_landing_page_event_metrics",
        ["url_id"],
    )
    op.create_index(
        "ix_ga_landing_events_date",
        "google_analytics_landing_page_event_metrics",
        ["date"],
    )
    op.create_index(
        "ix_ga_landing_events_event_name",
        "google_analytics_landing_page_event_metrics",
        ["event_name"],
    )


def downgrade() -> None:
    op.drop_table("google_analytics_landing_page_event_metrics")

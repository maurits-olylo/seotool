"""Store daily GA4 landing-page metrics."""

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"


def upgrade() -> None:
    op.create_table(
        "google_analytics_metrics",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("url_id", sa.Uuid()),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("landing_page", sa.String(2048), nullable=False),
        sa.Column("sessions", sa.Integer(), nullable=False),
        sa.Column("active_users", sa.Integer(), nullable=False),
        sa.Column("key_events", sa.Float(), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["url_id"], ["urls.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("website_id", "date", "landing_page"),
    )
    op.create_index(
        "ix_google_analytics_metrics_website_id",
        "google_analytics_metrics",
        ["website_id"],
    )
    op.create_index("ix_google_analytics_metrics_url_id", "google_analytics_metrics", ["url_id"])
    op.create_index("ix_google_analytics_metrics_date", "google_analytics_metrics", ["date"])


def downgrade() -> None:
    op.drop_table("google_analytics_metrics")

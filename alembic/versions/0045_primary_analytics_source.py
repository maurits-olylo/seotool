"""Add explicit primary analytics source.

Revision ID: 0045
Revises: 0044
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "website_settings",
        sa.Column("primary_analytics_source", sa.String(20), nullable=True),
    )
    op.create_check_constraint(
        "ck_website_settings_primary_analytics_source",
        "website_settings",
        "primary_analytics_source IS NULL OR primary_analytics_source IN ('ga4', 'matomo')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_website_settings_primary_analytics_source",
        "website_settings",
        type_="check",
    )
    op.drop_column("website_settings", "primary_analytics_source")

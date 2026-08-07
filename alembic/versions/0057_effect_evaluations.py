"""Add versioned cohort effect evaluations.

Revision ID: 0057
Revises: 0056
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0057"
down_revision: str | None = "0056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "effect_evaluations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("change_period_start", sa.Date(), nullable=False),
        sa.Column("change_period_end", sa.Date(), nullable=False),
        sa.Column("baseline_start", sa.Date(), nullable=False),
        sa.Column("baseline_end", sa.Date(), nullable=False),
        sa.Column("observation_start", sa.Date(), nullable=False),
        sa.Column("observation_end", sa.Date(), nullable=False),
        sa.Column("method_version", sa.String(30), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("analytics_source", sa.String(20)),
        sa.Column("intervention_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("url_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("metrics", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("source_coverage", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("confidence_factors", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('too_early', 'insufficient_data', 'not_comparable', 'development_visible')",
            name="ck_effect_evaluations_status",
        ),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "website_id", "input_hash", "method_version", name="uq_effect_evaluations_input_method"
        ),
    )
    for column in ("website_id", "method_version", "status"):
        op.create_index(f"ix_effect_evaluations_{column}", "effect_evaluations", [column])


def downgrade() -> None:
    op.drop_table("effect_evaluations")

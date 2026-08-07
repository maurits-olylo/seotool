"""Add versioned opportunity evaluation foundation.

Revision ID: 0055
Revises: 0054
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0055"
down_revision: str | None = "0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "opportunity_evaluations",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("primary_url_id", sa.Uuid()),
        sa.Column("scope_type", sa.String(30), nullable=False),
        sa.Column("scope_key", sa.String(255), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("formula_version", sa.String(50), nullable=False),
        sa.Column("potential_score", sa.Float()),
        sa.Column("friction_score", sa.Float()),
        sa.Column("evidence_score", sa.Float()),
        sa.Column("feasibility_score", sa.Float()),
        sa.Column("total_score", sa.Float()),
        sa.Column("priority_class", sa.String(30), nullable=False),
        sa.Column("source_coverage", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("contributors", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scope_type IN ('page', 'url_family', 'shared_cause')",
            name="ck_opportunity_evaluations_scope_type",
        ),
        sa.CheckConstraint(
            "priority_class IN ('high_opportunity', 'opportunity', 'monitor', "
            "'insufficient_evidence')",
            name="ck_opportunity_evaluations_priority_class",
        ),
        sa.CheckConstraint(
            "potential_score IS NULL OR potential_score BETWEEN 0 AND 100",
            name="ck_opportunity_evaluations_potential_score",
        ),
        sa.CheckConstraint(
            "friction_score IS NULL OR friction_score BETWEEN 0 AND 100",
            name="ck_opportunity_evaluations_friction_score",
        ),
        sa.CheckConstraint(
            "evidence_score IS NULL OR evidence_score BETWEEN 0 AND 100",
            name="ck_opportunity_evaluations_evidence_score",
        ),
        sa.CheckConstraint(
            "feasibility_score IS NULL OR feasibility_score BETWEEN 0 AND 100",
            name="ck_opportunity_evaluations_feasibility_score",
        ),
        sa.CheckConstraint(
            "total_score IS NULL OR total_score BETWEEN 0 AND 100",
            name="ck_opportunity_evaluations_total_score",
        ),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["primary_url_id"], ["urls.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "website_id",
            "scope_type",
            "scope_key",
            "input_hash",
            "formula_version",
            name="uq_opportunity_evaluation_input_formula",
        ),
    )
    indexed_columns = (
        "website_id",
        "primary_url_id",
        "scope_type",
        "formula_version",
        "priority_class",
    )
    for column in indexed_columns:
        op.create_index(f"ix_opportunity_evaluations_{column}", "opportunity_evaluations", [column])


def downgrade() -> None:
    op.drop_table("opportunity_evaluations")

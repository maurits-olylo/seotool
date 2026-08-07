"""Add immutable task-based effect interventions.

Revision ID: 0056
Revises: 0055
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0056"
down_revision: str | None = "0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "effect_interventions",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("implemented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("intervention_version", sa.String(30), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("task_snapshot", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("url_context", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("source_coverage", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["task_id"], ["recommendation_tasks.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("task_id", name="uq_effect_interventions_task"),
        sa.UniqueConstraint(
            "website_id",
            "input_hash",
            "intervention_version",
            name="uq_effect_interventions_input_version",
        ),
    )
    op.create_index(
        "ix_effect_interventions_website_id", "effect_interventions", ["website_id"]
    )
    op.create_index("ix_effect_interventions_task_id", "effect_interventions", ["task_id"])
    op.create_index(
        "ix_effect_interventions_implemented_at", "effect_interventions", ["implemented_at"]
    )


def downgrade() -> None:
    op.drop_table("effect_interventions")

"""Add deterministic query classification cache.

Revision ID: 0053
Revises: 0052
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0053"
down_revision: str | None = "0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "query_content_classifications",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("normalized_query", sa.String(2048), nullable=False),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("classification_version", sa.String(40), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("search_intent", sa.String(40), nullable=False),
        sa.Column("journey_stage", sa.String(40), nullable=False),
        sa.Column("content_role", sa.String(40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("probabilities", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "normalized_query",
            "language",
            "country",
            "classification_version",
            name="uq_query_content_classification_context_version",
        ),
    )
    op.create_index(
        "ix_query_content_classifications_search_intent",
        "query_content_classifications",
        ["search_intent"],
    )


def downgrade() -> None:
    op.drop_table("query_content_classifications")

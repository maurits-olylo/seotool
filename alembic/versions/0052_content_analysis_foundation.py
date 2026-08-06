"""Add content classification and evidence foundation.

Revision ID: 0052
Revises: 0051
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0052"
down_revision: str | None = "0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_analysis_settings",
        sa.Column("website_id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("branded_terms", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("sector_template", sa.String(80)),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "url_content_classifications",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("url_id", sa.Uuid(), nullable=False),
        sa.Column("period_start", sa.Date()),
        sa.Column("period_end", sa.Date()),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("classification_version", sa.String(40), nullable=False),
        sa.Column("search_intent", sa.String(40), nullable=False),
        sa.Column("journey_stage", sa.String(40), nullable=False),
        sa.Column("content_role", sa.String(40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("probabilities", sa.JSON(), nullable=False),
        sa.Column("source_coverage", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["url_id"], ["urls.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "url_id",
            "input_hash",
            "classification_version",
            name="uq_url_content_classification_input_version",
        ),
    )
    for column in ("website_id", "url_id", "search_intent", "journey_stage", "content_role"):
        op.create_index(
            f"ix_url_content_classifications_{column}",
            "url_content_classifications",
            [column],
        )
    op.create_table(
        "url_content_overrides",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("url_id", sa.Uuid(), nullable=False),
        sa.Column("search_intent", sa.String(40)),
        sa.Column("journey_stage", sa.String(40)),
        sa.Column("content_role", sa.String(40)),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("rationale", sa.Text()),
        sa.Column("updated_by_user_id", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["url_id"], ["urls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("url_id", name="uq_url_content_overrides_url"),
    )
    op.create_index("ix_url_content_overrides_website_id", "url_content_overrides", ["website_id"])
    op.create_index("ix_url_content_overrides_url_id", "url_content_overrides", ["url_id"])


def downgrade() -> None:
    op.drop_table("url_content_overrides")
    op.drop_table("url_content_classifications")
    op.drop_table("content_analysis_settings")

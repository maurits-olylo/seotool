"""Add bounded JavaScript render observations.

Revision ID: 0040
Revises: 0039
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "render_observations",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("url_id", sa.Uuid(), nullable=False),
        sa.Column("source_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("trigger_reasons", sa.JSON(), nullable=False),
        sa.Column("rendered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("browser_name", sa.String(length=80), nullable=True),
        sa.Column("rendered_word_count", sa.Integer(), nullable=True),
        sa.Column("rendered_main_content_hash", sa.String(length=64), nullable=True),
        sa.Column("rendered_metadata_hash", sa.String(length=64), nullable=True),
        sa.Column("rendered_links_hash", sa.String(length=64), nullable=True),
        sa.Column("rendered_schema_hash", sa.String(length=64), nullable=True),
        sa.Column("comparison", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_snapshot_id"], ["url_snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["url_id"], ["urls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_snapshot_id"),
    )
    op.create_index(
        op.f("ix_render_observations_website_id"), "render_observations", ["website_id"]
    )
    op.create_index(op.f("ix_render_observations_url_id"), "render_observations", ["url_id"])
    op.create_index(
        op.f("ix_render_observations_source_snapshot_id"),
        "render_observations",
        ["source_snapshot_id"],
    )
    op.create_index(op.f("ix_render_observations_status"), "render_observations", ["status"])


def downgrade() -> None:
    op.drop_table("render_observations")

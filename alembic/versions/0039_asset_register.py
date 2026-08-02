"""Add persistent asset register.

Revision ID: 0039
Revises: 0038
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("url_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("final_url", sa.String(length=2048), nullable=True),
        sa.Column("response_size", sa.Integer(), nullable=True),
        sa.Column("etag", sa.String(length=512), nullable=True),
        sa.Column("last_modified", sa.String(length=255), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["url_id"], ["urls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_assets_website_id"), "assets", ["website_id"])
    op.create_index(op.f("ix_assets_url_id"), "assets", ["url_id"], unique=True)
    op.create_index(op.f("ix_assets_kind"), "assets", ["kind"])
    op.create_index(op.f("ix_assets_content_type"), "assets", ["content_type"])
    op.create_index(op.f("ix_assets_status_code"), "assets", ["status_code"])
    op.create_index(op.f("ix_assets_last_checked_at"), "assets", ["last_checked_at"])


def downgrade() -> None:
    op.drop_table("assets")

"""Store Bing referring domain and anchor exports.

Revision ID: 0024
Revises: 0023
"""

import sqlalchemy as sa

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bing_referring_domains",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("domain", sa.String(length=2048), nullable=False),
        sa.Column("backlink_count", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("website_id", "domain"),
    )
    op.create_index(
        "ix_bing_referring_domains_website_id", "bing_referring_domains", ["website_id"]
    )
    op.create_index("ix_bing_referring_domains_is_active", "bing_referring_domains", ["is_active"])
    op.create_table(
        "bing_referring_anchors",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("anchor_key", sa.String(length=64), nullable=False),
        sa.Column("anchor_text", sa.Text(), nullable=False),
        sa.Column("backlink_count", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("website_id", "anchor_key"),
    )
    op.create_index(
        "ix_bing_referring_anchors_website_id", "bing_referring_anchors", ["website_id"]
    )
    op.create_index("ix_bing_referring_anchors_is_active", "bing_referring_anchors", ["is_active"])


def downgrade() -> None:
    op.drop_table("bing_referring_anchors")
    op.drop_table("bing_referring_domains")

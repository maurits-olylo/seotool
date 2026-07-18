"""Add persistent issue suppressions.

Revision ID: 0025
Revises: 0024
"""

import sqlalchemy as sa

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "issue_suppressions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("url_id", sa.Uuid(), nullable=False),
        sa.Column("issue_type", sa.String(length=100), nullable=False),
        sa.Column("actor", sa.String(length=320), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("restored_by", sa.String(length=320), nullable=True),
        sa.ForeignKeyConstraint(["url_id"], ["urls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("website_id", "url_id", "issue_type"),
    )
    op.create_index("ix_issue_suppressions_website_id", "issue_suppressions", ["website_id"])
    op.create_index("ix_issue_suppressions_url_id", "issue_suppressions", ["url_id"])
    op.create_index("ix_issue_suppressions_issue_type", "issue_suppressions", ["issue_type"])
    op.create_index("ix_issue_suppressions_is_active", "issue_suppressions", ["is_active"])


def downgrade() -> None:
    op.drop_table("issue_suppressions")

"""Store reportable internal work activity.

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activity_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("actor", sa.String(length=320)),
        sa.Column("activity_type", sa.String(length=80), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_activity_log_website_id", "activity_log", ["website_id"])
    op.create_index("ix_activity_log_activity_type", "activity_log", ["activity_type"])
    op.create_index("ix_activity_log_occurred_at", "activity_log", ["occurred_at"])


def downgrade() -> None:
    op.drop_table("activity_log")

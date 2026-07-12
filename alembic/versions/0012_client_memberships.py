"""Client-scoped memberships.

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_memberships",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "client_id"),
    )
    op.create_index("ix_client_memberships_user_id", "client_memberships", ["user_id"])
    op.create_index("ix_client_memberships_client_id", "client_memberships", ["client_id"])
    op.create_index("ix_client_memberships_role", "client_memberships", ["role"])


def downgrade() -> None:
    op.drop_table("client_memberships")

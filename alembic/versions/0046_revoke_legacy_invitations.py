"""Revoke legacy invitations before securing account acceptance.

Revision ID: 0046
Revises: 0045
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_invitations",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_user_invitations_revoked_at", "user_invitations", ["revoked_at"])
    op.execute(
        sa.text(
            "UPDATE user_invitations "
            "SET revoked_at = CURRENT_TIMESTAMP "
            "WHERE accepted_at IS NULL AND revoked_at IS NULL"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_user_invitations_revoked_at", table_name="user_invitations")
    op.drop_column("user_invitations", "revoked_at")

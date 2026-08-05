"""Add administrator MFA foundation.

Revision ID: 0050
Revises: 0049
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0050"
down_revision: str | None = "0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mfa_secret_encrypted", sa.String(1024)))
    op.add_column(
        "users",
        sa.Column("mfa_recovery_code_hashes", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "users",
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("users", sa.Column("mfa_last_counter", sa.BigInteger()))
    op.create_index("ix_users_mfa_enabled", "users", ["mfa_enabled"])


def downgrade() -> None:
    op.drop_index("ix_users_mfa_enabled", table_name="users")
    op.drop_column("users", "mfa_last_counter")
    op.drop_column("users", "mfa_enabled")
    op.drop_column("users", "mfa_recovery_code_hashes")
    op.drop_column("users", "mfa_secret_encrypted")

"""Add Matomo landing continuation evidence.

Revision ID: 0054
Revises: 0053
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0054"
down_revision: str | None = "0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in ("entry_visits", "bounces", "exits"):
        op.add_column(
            "matomo_page_metrics",
            sa.Column(column, sa.Integer(), nullable=False, server_default="0"),
        )
        op.alter_column("matomo_page_metrics", column, server_default=None)


def downgrade() -> None:
    for column in ("exits", "bounces", "entry_visits"):
        op.drop_column("matomo_page_metrics", column)

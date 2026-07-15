"""Store exact selection and filter context for page exports.

Revision ID: 0021
Revises: 0020
"""

import sqlalchemy as sa

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exports", sa.Column("item_ids", sa.JSON(), nullable=True))
    op.add_column("exports", sa.Column("filters", sa.JSON(), nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("exports", "filters")
    op.drop_column("exports", "item_ids")

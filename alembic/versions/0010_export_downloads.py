"""Track downloaded exports."""

import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"


def upgrade() -> None:
    op.add_column("exports", sa.Column("downloaded_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE exports SET downloaded_at = finished_at WHERE status = 'succeeded'")


def downgrade() -> None:
    op.drop_column("exports", "downloaded_at")

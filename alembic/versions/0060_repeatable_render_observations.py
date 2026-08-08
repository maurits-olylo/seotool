"""Allow repeatable render observations for explicit live rechecks.

Revision ID: 0060
Revises: 0059
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0060"
down_revision: str | None = "0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "render_observations_source_snapshot_id_key",
        "render_observations",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "render_observations_source_snapshot_id_key",
        "render_observations",
        ["source_snapshot_id"],
    )

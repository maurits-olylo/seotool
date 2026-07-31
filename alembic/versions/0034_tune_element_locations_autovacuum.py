"""Tune autovacuum for the large element locations table.

Revision ID: 0034
Revises: 0033
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AUTOVACUUM_OPTIONS = (
    "autovacuum_vacuum_scale_factor = 0.02, "
    "autovacuum_vacuum_threshold = 50000, "
    "autovacuum_analyze_scale_factor = 0.01, "
    "autovacuum_analyze_threshold = 25000"
)


def upgrade() -> None:
    op.execute(f"ALTER TABLE element_locations SET ({AUTOVACUUM_OPTIONS})")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE element_locations RESET ("
        "autovacuum_vacuum_scale_factor, "
        "autovacuum_vacuum_threshold, "
        "autovacuum_analyze_scale_factor, "
        "autovacuum_analyze_threshold"
        ")"
    )

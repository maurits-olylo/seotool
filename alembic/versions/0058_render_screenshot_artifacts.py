"""Add bounded render screenshot artifact metadata.

Revision ID: 0058
Revises: 0057
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0058"
down_revision: str | None = "0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in (
        sa.Column("screenshot_key", sa.String(255)),
        sa.Column("screenshot_sha256", sa.String(64)),
        sa.Column("screenshot_bytes", sa.BigInteger()),
        sa.Column("screenshot_width", sa.Integer()),
        sa.Column("screenshot_height", sa.Integer()),
        sa.Column("screenshot_expires_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("render_observations", column)
    op.create_unique_constraint(
        "uq_render_observations_screenshot_key", "render_observations", ["screenshot_key"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_render_observations_screenshot_key", "render_observations", type_="unique"
    )
    for name in (
        "screenshot_expires_at",
        "screenshot_height",
        "screenshot_width",
        "screenshot_bytes",
        "screenshot_sha256",
        "screenshot_key",
    ):
        op.drop_column("render_observations", name)

"""Store detected and confirmed website platforms.

Revision ID: 0064
Revises: 0063
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0064"
down_revision: str | None = "0063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("website_onboardings", sa.Column("detected_platform", sa.String(40)))
    op.add_column("website_onboardings", sa.Column("platform_confidence", sa.String(20)))
    op.add_column("website_onboardings", sa.Column("confirmed_platform", sa.String(40)))


def downgrade() -> None:
    op.drop_column("website_onboardings", "confirmed_platform")
    op.drop_column("website_onboardings", "platform_confidence")
    op.drop_column("website_onboardings", "detected_platform")

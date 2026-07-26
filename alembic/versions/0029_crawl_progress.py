"""Add phase-aware crawl progress and heartbeat fields.

Revision ID: 0029
Revises: 0028
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("crawl_runs", sa.Column("phase", sa.String(length=40), nullable=True))
    op.add_column(
        "crawl_runs",
        sa.Column("phase_current", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "crawl_runs",
        sa.Column("phase_total", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "crawl_runs",
        sa.Column("html_urls", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "crawl_runs",
        sa.Column("asset_urls", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "crawl_runs",
        sa.Column("skipped_urls", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "crawl_runs",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE crawl_runs SET html_urls = crawled_urls")


def downgrade() -> None:
    op.drop_column("crawl_runs", "heartbeat_at")
    op.drop_column("crawl_runs", "skipped_urls")
    op.drop_column("crawl_runs", "asset_urls")
    op.drop_column("crawl_runs", "html_urls")
    op.drop_column("crawl_runs", "phase_total")
    op.drop_column("crawl_runs", "phase_current")
    op.drop_column("crawl_runs", "phase")

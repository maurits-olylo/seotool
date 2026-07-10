"""Persist crawl depth for full site crawls."""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"


def upgrade() -> None:
    op.add_column("urls", sa.Column("crawl_depth", sa.Integer()))
    op.create_index("ix_urls_crawl_depth", "urls", ["crawl_depth"])


def downgrade() -> None:
    op.drop_index("ix_urls_crawl_depth", table_name="urls")
    op.drop_column("urls", "crawl_depth")

"""Guard parallel crawl workers per website.

Revision ID: 0027
Revises: 0026
"""

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_crawl_jobs_running_website",
        "crawl_jobs",
        ["website_id"],
        unique=True,
        postgresql_where=text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index("uq_crawl_jobs_running_website", table_name="crawl_jobs")

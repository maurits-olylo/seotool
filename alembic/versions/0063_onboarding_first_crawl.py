"""Persist the single first crawl created by website onboarding.

Revision ID: 0063
Revises: 0062
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0063"
down_revision: str | None = "0062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "website_onboardings",
        sa.Column("first_crawl_job_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_website_onboardings_first_crawl_job",
        "website_onboardings",
        "crawl_jobs",
        ["first_crawl_job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_website_onboarding_first_crawl_job",
        "website_onboardings",
        ["first_crawl_job_id"],
    )
    op.create_index(
        "ix_website_onboardings_first_crawl_job_id",
        "website_onboardings",
        ["first_crawl_job_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_website_onboardings_first_crawl_job_id",
        table_name="website_onboardings",
    )
    op.drop_constraint(
        "uq_website_onboarding_first_crawl_job",
        "website_onboardings",
        type_="unique",
    )
    op.drop_constraint(
        "fk_website_onboardings_first_crawl_job",
        "website_onboardings",
        type_="foreignkey",
    )
    op.drop_column("website_onboardings", "first_crawl_job_id")

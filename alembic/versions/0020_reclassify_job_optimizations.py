"""Reclassify optional JobPosting fields as optimizations.

Revision ID: 0020
Revises: 0019
"""

import sqlalchemy as sa

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    issues = sa.table(
        "issues",
        sa.column("issue_type", sa.String()),
        sa.column("category", sa.String()),
        sa.column("confidence", sa.String()),
        sa.column("title", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("recommended_action", sa.Text()),
    )
    op.get_bind().execute(
        issues.update()
        .where(issues.c.issue_type == "job_posting_missing_recommended_fields")
        .values(
            category="optimization",
            confidence="low",
            title="JobPosting kan worden aangevuld",
            description="Een of meer optionele JobPosting-velden ontbreken.",
            recommended_action=(
                "Overweeg de ontbrekende optionele velden toe te voegen voor vollediger "
                "vacature-schema. Deze velden zijn niet verplicht en de verwachte SEO-impact "
                "is minimaal."
            ),
        )
    )


def downgrade() -> None:
    issues = sa.table(
        "issues",
        sa.column("issue_type", sa.String()),
        sa.column("category", sa.String()),
        sa.column("confidence", sa.String()),
        sa.column("title", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("recommended_action", sa.Text()),
    )
    op.get_bind().execute(
        issues.update()
        .where(issues.c.issue_type == "job_posting_missing_recommended_fields")
        .values(
            category="structured_data",
            confidence="high",
            title="JobPosting mist aanbevolen velden",
            description="Een of meer aanbevolen JobPosting-velden ontbreken.",
            recommended_action=(
                "Vul employmentType en een stabiele identifier aan voor vollediger vacature-schema."
            ),
        )
    )

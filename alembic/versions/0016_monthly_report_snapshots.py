"""Store immutable customer reports for closed calendar months.

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monthly_report_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("website_id", "period_start"),
    )
    op.create_index(
        "ix_monthly_report_snapshots_website_id", "monthly_report_snapshots", ["website_id"]
    )
    op.create_index(
        "ix_monthly_report_snapshots_period_start", "monthly_report_snapshots", ["period_start"]
    )
    op.create_index(
        "ix_monthly_report_snapshots_generated_at", "monthly_report_snapshots", ["generated_at"]
    )


def downgrade() -> None:
    op.drop_table("monthly_report_snapshots")

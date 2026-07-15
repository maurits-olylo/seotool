"""Add durable global crawl deployment control.

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
    control = op.create_table(
        "crawl_deployment_control",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("paused_job_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_crawl_deployment_control_singleton"),
    )
    op.bulk_insert(control, [{"id": 1, "is_active": False, "paused_job_ids": []}])


def downgrade() -> None:
    op.drop_table("crawl_deployment_control")

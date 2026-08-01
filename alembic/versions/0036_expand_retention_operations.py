"""Expand durable retention operations to multiple datasets.

Revision ID: 0036
Revises: 0035
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "retention_operations",
        sa.Column(
            "dataset",
            sa.String(length=80),
            nullable=False,
            server_default="element_locations",
        ),
    )
    op.add_column(
        "retention_operations",
        sa.Column(
            "policy_version",
            sa.String(length=40),
            nullable=False,
            server_default="2026-08-02-v1",
        ),
    )
    op.add_column(
        "retention_operations",
        sa.Column("before_report", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "retention_operations",
        sa.Column("after_report", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.drop_constraint(
        "retention_operations_trigger_crawl_run_id_key",
        "retention_operations",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_retention_operations_trigger_dataset",
        "retention_operations",
        ["trigger_crawl_run_id", "dataset"],
    )
    op.create_index(
        op.f("ix_retention_operations_dataset"),
        "retention_operations",
        ["dataset"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_retention_operations_dataset"), table_name="retention_operations")
    op.drop_constraint(
        "uq_retention_operations_trigger_dataset",
        "retention_operations",
        type_="unique",
    )
    op.create_unique_constraint(
        "retention_operations_trigger_crawl_run_id_key",
        "retention_operations",
        ["trigger_crawl_run_id"],
    )
    op.drop_column("retention_operations", "after_report")
    op.drop_column("retention_operations", "before_report")
    op.drop_column("retention_operations", "policy_version")
    op.drop_column("retention_operations", "dataset")

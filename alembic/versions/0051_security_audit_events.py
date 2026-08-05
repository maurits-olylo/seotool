"""Add append-only security audit events.

Revision ID: 0051
Revises: 0050
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0051"
down_revision: str | None = "0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "security_audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_user_id", sa.Uuid()),
        sa.Column("client_id", sa.Uuid()),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("target_type", sa.String(50)),
        sa.Column("target_id", sa.String(255)),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("source_hash", sa.String(64)),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="SET NULL"),
    )
    for column in (
        "actor_user_id",
        "client_id",
        "event_type",
        "target_id",
        "result",
        "occurred_at",
    ):
        op.create_index(
            f"ix_security_audit_events_{column}", "security_audit_events", [column]
        )


def downgrade() -> None:
    op.drop_table("security_audit_events")

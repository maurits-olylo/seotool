"""Add queue policy metadata and durable dead letters.

Revision ID: 0037
Revises: 0036
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "website_settings",
        sa.Column("queue_priority", sa.Integer(), nullable=False, server_default="50"),
    )
    op.add_column(
        "website_settings",
        sa.Column("crawl_queue_limit", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_website_settings_queue_priority",
        "website_settings",
        "queue_priority BETWEEN 0 AND 100",
    )
    op.create_check_constraint(
        "ck_website_settings_crawl_queue_limit",
        "website_settings",
        "crawl_queue_limit BETWEEN 1 AND 5",
    )
    op.add_column("crawl_jobs", sa.Column("queue_name", sa.String(length=50), nullable=True))
    op.add_column(
        "crawl_jobs",
        sa.Column("queue_priority", sa.Integer(), nullable=False, server_default="50"),
    )
    op.create_index(op.f("ix_crawl_jobs_queue_name"), "crawl_jobs", ["queue_name"])
    op.create_index(op.f("ix_crawl_jobs_queue_priority"), "crawl_jobs", ["queue_priority"])
    op.create_check_constraint(
        "ck_crawl_jobs_queue_priority",
        "crawl_jobs",
        "queue_priority BETWEEN 0 AND 100",
    )
    op.create_table(
        "queue_dead_letters",
        sa.Column("website_id", sa.Uuid(), nullable=True),
        sa.Column("queue_name", sa.String(length=50), nullable=False),
        sa.Column("original_job_id", sa.String(length=255), nullable=False),
        sa.Column("job_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="unresolved"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("queue_name", "original_job_id", name="uq_dead_letter_queue_job"),
    )
    op.create_index(op.f("ix_queue_dead_letters_website_id"), "queue_dead_letters", ["website_id"])
    op.create_index(op.f("ix_queue_dead_letters_queue_name"), "queue_dead_letters", ["queue_name"])
    op.create_index(op.f("ix_queue_dead_letters_job_type"), "queue_dead_letters", ["job_type"])
    op.create_index(op.f("ix_queue_dead_letters_status"), "queue_dead_letters", ["status"])
    op.create_index(op.f("ix_queue_dead_letters_failed_at"), "queue_dead_letters", ["failed_at"])


def downgrade() -> None:
    op.drop_table("queue_dead_letters")
    op.drop_constraint("ck_crawl_jobs_queue_priority", "crawl_jobs", type_="check")
    op.drop_index(op.f("ix_crawl_jobs_queue_priority"), table_name="crawl_jobs")
    op.drop_index(op.f("ix_crawl_jobs_queue_name"), table_name="crawl_jobs")
    op.drop_column("crawl_jobs", "queue_priority")
    op.drop_column("crawl_jobs", "queue_name")
    op.drop_constraint("ck_website_settings_crawl_queue_limit", "website_settings", type_="check")
    op.drop_constraint("ck_website_settings_queue_priority", "website_settings", type_="check")
    op.drop_column("website_settings", "crawl_queue_limit")
    op.drop_column("website_settings", "queue_priority")

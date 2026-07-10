"""Changes and issue lifecycle."""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"


def upgrade() -> None:
    op.create_table(
        "changes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "website_id",
            sa.Uuid(),
            sa.ForeignKey("websites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "url_id", sa.Uuid(), sa.ForeignKey("urls.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "previous_snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("url_snapshots.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "current_snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("url_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("change_type", sa.String(50), nullable=False),
        sa.Column("field_name", sa.String(100)),
        sa.Column("old_value", sa.Text()),
        sa.Column("new_value", sa.Text()),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("website_id", "url_id", "current_snapshot_id", "change_type"):
        op.create_index(f"ix_changes_{column}", "changes", [column])
    op.create_table(
        "issues",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "website_id",
            sa.Uuid(),
            sa.ForeignKey("websites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url_id", sa.Uuid(), sa.ForeignKey("urls.id", ondelete="CASCADE")),
        sa.Column("issue_type", sa.String(100), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("assigned_to", sa.String(255)),
        sa.Column("due_date", sa.Date()),
        sa.UniqueConstraint("website_id", "url_id", "issue_type"),
    )
    for column in ("website_id", "url_id", "issue_type", "category", "severity", "status"):
        op.create_index(f"ix_issues_{column}", "issues", [column])
    op.create_table(
        "issue_occurrences",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "issue_id", sa.Uuid(), sa.ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "crawl_run_id",
            sa.Uuid(),
            sa.ForeignKey("crawl_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("snapshot_id", sa.Uuid(), sa.ForeignKey("url_snapshots.id", ondelete="SET NULL")),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.UniqueConstraint("issue_id", "crawl_run_id"),
    )
    op.create_index("ix_issue_occurrences_issue_id", "issue_occurrences", ["issue_id"])
    op.create_index("ix_issue_occurrences_crawl_run_id", "issue_occurrences", ["crawl_run_id"])
    op.create_table(
        "issue_comments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "issue_id", sa.Uuid(), sa.ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("author", sa.String(255), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_issue_comments_issue_id", "issue_comments", ["issue_id"])


def downgrade() -> None:
    op.drop_table("issue_comments")
    op.drop_table("issue_occurrences")
    op.drop_table("issues")
    op.drop_table("changes")

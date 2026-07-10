"""URL registry, sources and crawl jobs."""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.create_table(
        "urls",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "website_id",
            sa.Uuid(),
            sa.ForeignKey("websites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("normalized_url", sa.String(2048), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_status_code", sa.Integer()),
        sa.Column("current_final_url", sa.String(2048)),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_indexable", sa.Boolean()),
        sa.Column("is_important", sa.Boolean(), nullable=False),
        sa.Column("page_type", sa.String(50)),
        sa.Column("last_light_checked_at", sa.DateTime(timezone=True)),
        sa.Column("last_full_analyzed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("website_id", "normalized_url"),
    )
    op.create_index("ix_urls_website_id", "urls", ["website_id"])
    op.create_index("ix_urls_is_active", "urls", ["is_active"])
    op.create_table(
        "url_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "url_id", sa.Uuid(), sa.ForeignKey("urls.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_url", sa.String(2048), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("url_id", "source_type", "source_url"),
    )
    op.create_index("ix_url_sources_url_id", "url_sources", ["url_id"])
    op.create_index("ix_url_sources_source_type", "url_sources", ["source_type"])
    op.create_table(
        "crawl_jobs",
        sa.Column(
            "website_id",
            sa.Uuid(),
            sa.ForeignKey("websites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("settings_snapshot", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_crawl_jobs_website_id", "crawl_jobs", ["website_id"])
    op.create_index("ix_crawl_jobs_job_type", "crawl_jobs", ["job_type"])
    op.create_index("ix_crawl_jobs_status", "crawl_jobs", ["status"])


def downgrade() -> None:
    op.drop_table("crawl_jobs")
    op.drop_table("url_sources")
    op.drop_table("urls")

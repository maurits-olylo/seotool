"""Crawler runs, URL snapshots and links."""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    op.create_table(
        "crawl_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "crawl_job_id",
            sa.Uuid(),
            sa.ForeignKey("crawl_jobs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "website_id",
            sa.Uuid(),
            sa.ForeignKey("websites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("crawl_type", sa.String(40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("discovered_urls", sa.Integer(), nullable=False),
        sa.Column("crawled_urls", sa.Integer(), nullable=False),
        sa.Column("failed_urls", sa.Integer(), nullable=False),
    )
    op.create_index("ix_crawl_runs_crawl_job_id", "crawl_runs", ["crawl_job_id"])
    op.create_index("ix_crawl_runs_website_id", "crawl_runs", ["website_id"])
    op.create_index("ix_crawl_runs_status", "crawl_runs", ["status"])
    op.create_table(
        "url_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "url_id", sa.Uuid(), sa.ForeignKey("urls.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "crawl_run_id",
            sa.Uuid(),
            sa.ForeignKey("crawl_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_url", sa.String(2048), nullable=False),
        sa.Column("final_url", sa.String(2048)),
        sa.Column("status_code", sa.Integer()),
        sa.Column("redirect_chain", sa.JSON(), nullable=False),
        sa.Column("content_type", sa.String(255)),
        sa.Column("response_time_ms", sa.Integer()),
        sa.Column("response_size", sa.Integer()),
        sa.Column("etag", sa.String(512)),
        sa.Column("last_modified", sa.String(255)),
        sa.Column("title", sa.Text()),
        sa.Column("meta_description", sa.Text()),
        sa.Column("canonical", sa.String(2048)),
        sa.Column("meta_robots", sa.String(512)),
        sa.Column("x_robots_tag", sa.String(512)),
        sa.Column("html_lang", sa.String(50)),
        sa.Column("headings", sa.JSON(), nullable=False),
        sa.Column("word_count", sa.Integer()),
        sa.Column("main_content", sa.Text()),
        sa.Column("schema_types", sa.JSON(), nullable=False),
        sa.Column("schema_data", sa.JSON(), nullable=False),
        sa.Column("html_hash", sa.String(64)),
        sa.Column("main_content_hash", sa.String(64)),
        sa.Column("metadata_hash", sa.String(64)),
        sa.Column("links_hash", sa.String(64)),
        sa.Column("schema_hash", sa.String(64)),
        sa.Column("is_indexable", sa.Boolean()),
        sa.Column("error_message", sa.Text()),
    )
    op.create_index("ix_url_snapshots_url_id", "url_snapshots", ["url_id"])
    op.create_index("ix_url_snapshots_crawl_run_id", "url_snapshots", ["crawl_run_id"])
    op.create_index("ix_url_snapshots_checked_at", "url_snapshots", ["checked_at"])
    op.create_table(
        "url_links",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "crawl_run_id",
            sa.Uuid(),
            sa.ForeignKey("crawl_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_url_id", sa.Uuid(), sa.ForeignKey("urls.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("target_url", sa.String(2048), nullable=False),
        sa.Column("target_url_id", sa.Uuid(), sa.ForeignKey("urls.id", ondelete="SET NULL")),
        sa.Column("anchor_text", sa.Text(), nullable=False),
        sa.Column("is_internal", sa.Boolean(), nullable=False),
        sa.Column("is_nofollow", sa.Boolean(), nullable=False),
        sa.Column("http_status", sa.Integer()),
    )
    op.create_index("ix_url_links_crawl_run_id", "url_links", ["crawl_run_id"])
    op.create_index("ix_url_links_source_url_id", "url_links", ["source_url_id"])


def downgrade() -> None:
    op.drop_table("url_links")
    op.drop_table("url_snapshots")
    op.drop_table("crawl_runs")

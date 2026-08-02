"""Add canonical, hreflang and URL Inspection storage.

Revision ID: 0038
Revises: 0037
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "url_snapshots",
        sa.Column("canonical_urls", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "url_snapshots",
        sa.Column("hreflang_links", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.create_table(
        "url_inspection_results",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("url_id", sa.Uuid(), nullable=False),
        sa.Column("inspected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("inspection_result_link", sa.String(length=2048), nullable=True),
        sa.Column("verdict", sa.String(length=40), nullable=True),
        sa.Column("coverage_state", sa.String(length=255), nullable=True),
        sa.Column("indexing_state", sa.String(length=80), nullable=True),
        sa.Column("page_fetch_state", sa.String(length=80), nullable=True),
        sa.Column("robots_txt_state", sa.String(length=80), nullable=True),
        sa.Column("last_crawl_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("google_canonical", sa.String(length=2048), nullable=True),
        sa.Column("user_canonical", sa.String(length=2048), nullable=True),
        sa.Column("referring_urls", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("sitemap_urls", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("rich_results", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("raw_response", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["url_id"], ["urls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_url_inspection_results_website_id"),
        "url_inspection_results",
        ["website_id"],
    )
    op.create_index(
        op.f("ix_url_inspection_results_url_id"), "url_inspection_results", ["url_id"]
    )
    op.create_index(
        op.f("ix_url_inspection_results_inspected_at"),
        "url_inspection_results",
        ["inspected_at"],
    )
    op.create_index(
        op.f("ix_url_inspection_results_verdict"), "url_inspection_results", ["verdict"]
    )


def downgrade() -> None:
    op.drop_table("url_inspection_results")
    op.drop_column("url_snapshots", "hreflang_links")
    op.drop_column("url_snapshots", "canonical_urls")

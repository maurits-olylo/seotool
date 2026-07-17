"""Store generic live element locations.

Revision ID: 0023
Revises: 0022
"""

import sqlalchemy as sa

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "element_locations",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("source_url_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("crawl_run_id", sa.Uuid(), nullable=False),
        sa.Column("issue_types", sa.JSON(), nullable=False),
        sa.Column("element_type", sa.String(length=40), nullable=False),
        sa.Column("target_url", sa.String(length=2048), nullable=True),
        sa.Column("visible_text", sa.Text(), nullable=True),
        sa.Column("element_id", sa.String(length=512), nullable=True),
        sa.Column("css_selector", sa.Text(), nullable=True),
        sa.Column("xpath", sa.Text(), nullable=True),
        sa.Column("html_fragment", sa.Text(), nullable=False),
        sa.Column("occurrence_index", sa.Integer(), nullable=False),
        sa.Column("text_prefix", sa.Text(), nullable=True),
        sa.Column("text_suffix", sa.Text(), nullable=True),
        sa.Column("text_is_unique", sa.Boolean(), nullable=False),
        sa.Column("context_is_unique", sa.Boolean(), nullable=False),
        sa.Column("rendered_dynamically", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["crawl_run_id"], ["crawl_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["url_snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_url_id"], ["urls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_element_locations_website_id", "element_locations", ["website_id"])
    op.create_index("ix_element_locations_source_url_id", "element_locations", ["source_url_id"])
    op.create_index("ix_element_locations_snapshot_id", "element_locations", ["snapshot_id"])
    op.create_index("ix_element_locations_crawl_run_id", "element_locations", ["crawl_run_id"])
    op.create_index("ix_element_locations_element_type", "element_locations", ["element_type"])


def downgrade() -> None:
    op.drop_table("element_locations")

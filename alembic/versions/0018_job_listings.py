"""Store recognized vacancies independently from crawl snapshots.

Revision ID: 0018
Revises: 0017
"""

import sqlalchemy as sa

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_listings",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("url_id", sa.Uuid(), nullable=False),
        sa.Column("latest_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("detection_sources", sa.JSON(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("employer", sa.String(length=512), nullable=True),
        sa.Column("locations", sa.JSON(), nullable=False),
        sa.Column("date_posted", sa.Date(), nullable=True),
        sa.Column("valid_through", sa.Date(), nullable=True),
        sa.Column("salary_data", sa.JSON(), nullable=False),
        sa.Column("hours", sa.String(length=255), nullable=True),
        sa.Column("employment_types", sa.JSON(), nullable=False),
        sa.Column("external_identifier", sa.String(length=512), nullable=True),
        sa.Column("application_url", sa.String(length=2048), nullable=True),
        sa.Column("job_posting_data", sa.JSON(), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=30), nullable=False),
        sa.Column("manual_status", sa.String(length=30), nullable=True),
        sa.Column("current_status_code", sa.Integer(), nullable=True),
        sa.Column("is_indexable", sa.Boolean(), nullable=True),
        sa.Column("inbound_internal_links", sa.Integer(), nullable=False),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["url_id"], ["urls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["latest_snapshot_id"], ["url_snapshots.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("website_id", "url_id"),
    )
    for name, columns in (
        ("ix_job_listings_website_id", ["website_id"]),
        ("ix_job_listings_url_id", ["url_id"]),
        ("ix_job_listings_latest_snapshot_id", ["latest_snapshot_id"]),
        ("ix_job_listings_valid_through", ["valid_through"]),
        ("ix_job_listings_lifecycle_status", ["lifecycle_status"]),
        ("ix_job_listings_manual_status", ["manual_status"]),
        ("ix_job_listings_first_detected_at", ["first_detected_at"]),
        ("ix_job_listings_last_detected_at", ["last_detected_at"]),
    ):
        op.create_index(name, "job_listings", columns)


def downgrade() -> None:
    op.drop_table("job_listings")

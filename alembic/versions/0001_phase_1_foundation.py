"""Phase 1 foundation."""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("contact_name", sa.String(255)),
        sa.Column("contact_email", sa.String(320)),
        sa.Column("internal_reference", sa.String(100), unique=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_clients_name", "clients", ["name"])
    op.create_index("ix_clients_status", "clients", ["status"])
    op.create_table(
        "websites",
        sa.Column(
            "client_id", sa.Uuid(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("base_url", sa.String(2048), nullable=False),
        sa.Column("language", sa.String(10)),
        sa.Column("country", sa.String(2)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("client_id", "base_url"),
    )
    op.create_index("ix_websites_client_id", "websites", ["client_id"])
    op.create_index("ix_websites_status", "websites", ["status"])
    op.create_table(
        "website_settings",
        sa.Column(
            "website_id",
            sa.Uuid(),
            sa.ForeignKey("websites.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("sitemap_urls", sa.JSON(), nullable=False),
        sa.Column("allowed_subdomains", sa.JSON(), nullable=False),
        sa.Column("excluded_url_patterns", sa.JSON(), nullable=False),
        sa.Column("ignored_query_parameters", sa.JSON(), nullable=False),
        sa.Column("max_urls", sa.Integer(), nullable=False),
        sa.Column("request_delay_ms", sa.Integer(), nullable=False),
        sa.Column("concurrency", sa.Integer(), nullable=False),
        sa.Column("request_timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("max_response_size", sa.Integer(), nullable=False),
        sa.Column("respect_robots_txt", sa.Boolean(), nullable=False),
        sa.Column("light_check_interval", sa.Text(), nullable=False),
        sa.Column("full_crawl_interval", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("website_settings")
    op.drop_table("websites")
    op.drop_table("clients")

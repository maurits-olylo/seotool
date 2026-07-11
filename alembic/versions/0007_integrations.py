"""Client data-source connections and website property mappings."""

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"


def upgrade() -> None:
    op.create_table(
        "integration_connections",
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("account_email", sa.String(320)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("encrypted_access_token", sa.Text()),
        sa.Column("encrypted_refresh_token", sa.Text()),
        sa.Column("token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("client_id", "provider"),
    )
    op.create_index(
        "ix_integration_connections_client_id", "integration_connections", ["client_id"]
    )
    op.create_index("ix_integration_connections_provider", "integration_connections", ["provider"])
    op.create_index("ix_integration_connections_status", "integration_connections", ["status"])
    op.create_table(
        "website_integrations",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("service", sa.String(40), nullable=False),
        sa.Column("external_property_id", sa.String(512), nullable=False),
        sa.Column("external_property_name", sa.String(512)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["integration_connections.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("website_id", "service"),
    )
    op.create_index("ix_website_integrations_website_id", "website_integrations", ["website_id"])
    op.create_index(
        "ix_website_integrations_connection_id", "website_integrations", ["connection_id"]
    )
    op.create_index("ix_website_integrations_service", "website_integrations", ["service"])
    op.create_index("ix_website_integrations_status", "website_integrations", ["status"])


def downgrade() -> None:
    op.drop_table("website_integrations")
    op.drop_table("integration_connections")

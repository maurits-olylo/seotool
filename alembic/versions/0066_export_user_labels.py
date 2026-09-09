"""Allow export workers to read only assignee labels.

Revision ID: 0066
Revises: 0065
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0066"
down_revision: str | None = "0065"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_context().dialect.name == "postgresql":
        op.execute("""
            DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'seo_export') THEN
                    GRANT SELECT (id, display_name, email) ON TABLE public.users TO seo_export;
                END IF;
            END $$;
        """)


def downgrade() -> None:
    if op.get_context().dialect.name == "postgresql":
        op.execute("""
            DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'seo_export') THEN
                    REVOKE SELECT (id, display_name, email) ON TABLE public.users FROM seo_export;
                END IF;
            END $$;
        """)

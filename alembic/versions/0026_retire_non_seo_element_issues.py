"""Retire element checks that are not standalone SEO issues.

Revision ID: 0026
Revises: 0025
"""

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE issues
        SET status = 'ignored', resolved_at = NULL, verified_at = NULL
        WHERE issue_type IN ('duplicate_heading_text', 'invalid_or_empty_link')
          AND status NOT IN ('ignored', 'verified')
        """
    )


def downgrade() -> None:
    # Historical status cannot safely be reconstructed after retirement.
    pass

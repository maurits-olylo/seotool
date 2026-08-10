"""Add resumable website onboarding and ownership verification.

Revision ID: 0062
Revises: 0061
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0062"
down_revision: str | None = "0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "website_onboardings",
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("started_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("current_step", sa.String(length=30), nullable=False),
        sa.Column("last_error_code", sa.String(length=50), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('verification_pending', 'verified', 'crawl_queued', 'completed', 'failed')",
            name="ck_website_onboardings_status",
        ),
        sa.CheckConstraint(
            "current_step IN ('verification', 'crawl_preferences', 'first_crawl', 'results')",
            name="ck_website_onboardings_step",
        ),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["started_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", "request_id", name="uq_website_onboarding_request"),
        sa.UniqueConstraint("website_id", name="uq_website_onboarding_website"),
    )
    for column in (
        "client_id",
        "website_id",
        "started_by_user_id",
        "request_id",
        "status",
        "current_step",
    ):
        op.create_index(f"ix_website_onboardings_{column}", "website_onboardings", [column])

    op.create_table(
        "website_ownership_verifications",
        sa.Column("onboarding_id", sa.Uuid(), nullable=False),
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("method = 'https_file'", name="ck_website_verifications_method"),
        sa.CheckConstraint(
            "status IN ('pending', 'verified', 'expired')",
            name="ck_website_verifications_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_website_verifications_attempts"),
        sa.ForeignKeyConstraint(["onboarding_id"], ["website_onboardings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("onboarding_id", name="uq_website_verification_onboarding"),
        sa.UniqueConstraint("token_hash", name="uq_website_verification_token_hash"),
    )
    for column in ("onboarding_id", "website_id", "status", "expires_at"):
        op.create_index(
            f"ix_website_ownership_verifications_{column}",
            "website_ownership_verifications",
            [column],
        )


def downgrade() -> None:
    op.drop_table("website_ownership_verifications")
    op.drop_table("website_onboardings")

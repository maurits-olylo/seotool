"""Add disabled external intelligence persistence and cost controls.

Revision ID: 0059
Revises: 0058
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0059"
down_revision: str | None = "0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "website_settings",
        sa.Column(
            "external_intelligence_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "website_settings",
        sa.Column(
            "external_monthly_budget_micros", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "website_settings",
        sa.Column("external_active_scope_limit", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_website_settings_external_budget",
        "website_settings",
        "external_monthly_budget_micros >= 0",
    )
    op.create_check_constraint(
        "ck_website_settings_external_scope_limit",
        "website_settings",
        "external_active_scope_limit >= 0",
    )

    op.create_table(
        "external_intelligence_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("url_id", sa.Uuid()),
        sa.Column("capability", sa.String(30), nullable=False),
        sa.Column("cache_key", sa.String(512), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("provider", sa.String(40)),
        sa.Column("request_context", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("budget_snapshot", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("estimated_cost_micros", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actual_cost_micros", sa.Integer()),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "capability IN ('serp', 'ai_citations')", name="ck_external_requests_capability"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_external_requests_status",
        ),
        sa.CheckConstraint(
            "estimated_cost_micros >= 0 AND "
            "(actual_cost_micros IS NULL OR actual_cost_micros >= 0)",
            name="ck_external_requests_costs",
        ),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["url_id"], ["urls.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "website_id",
            "capability",
            "idempotency_key",
            name="uq_external_request_idempotency",
        ),
        sa.UniqueConstraint("id", "website_id", name="uq_external_request_tenant"),
    )
    for column in ("website_id", "url_id", "capability", "cache_key", "status"):
        op.create_index(
            f"ix_external_intelligence_requests_{column}",
            "external_intelligence_requests",
            [column],
        )

    op.create_table(
        "external_observations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("capability", sa.String(30), nullable=False),
        sa.Column("cache_key", sa.String(512), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("normalized_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("source_coverage", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "capability IN ('serp', 'ai_citations')",
            name="ck_external_observations_capability",
        ),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["request_id", "website_id"],
            ["external_intelligence_requests.id", "external_intelligence_requests.website_id"],
            ondelete="CASCADE",
            name="fk_external_observation_request_tenant",
        ),
        sa.UniqueConstraint("request_id", "evidence_hash", name="uq_external_observation_evidence"),
    )
    for column in (
        "website_id",
        "request_id",
        "capability",
        "cache_key",
        "observed_at",
        "expires_at",
    ):
        op.create_index(f"ix_external_observations_{column}", "external_observations", [column])

    op.create_table(
        "external_usage_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("capability", sa.String(30), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_micros", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actual_cost_micros", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "capability IN ('serp', 'ai_citations')", name="ck_external_usage_capability"
        ),
        sa.CheckConstraint(
            "estimated_cost_micros >= 0 AND actual_cost_micros >= 0 AND units >= 0",
            name="ck_external_usage_values",
        ),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["request_id", "website_id"],
            ["external_intelligence_requests.id", "external_intelligence_requests.website_id"],
            ondelete="CASCADE",
            name="fk_external_usage_request_tenant",
        ),
        sa.UniqueConstraint("request_id", name="uq_external_usage_request"),
    )
    for column in ("website_id", "request_id", "capability", "recorded_at"):
        op.create_index(f"ix_external_usage_records_{column}", "external_usage_records", [column])


def downgrade() -> None:
    op.drop_table("external_usage_records")
    op.drop_table("external_observations")
    op.drop_table("external_intelligence_requests")
    op.drop_constraint(
        "ck_website_settings_external_scope_limit", "website_settings", type_="check"
    )
    op.drop_constraint("ck_website_settings_external_budget", "website_settings", type_="check")
    op.drop_column("website_settings", "external_active_scope_limit")
    op.drop_column("website_settings", "external_monthly_budget_micros")
    op.drop_column("website_settings", "external_intelligence_enabled")

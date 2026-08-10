"""Add canonical Sensor measurement foundation.

Revision ID: 0061
Revises: 0060
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0061"
down_revision: str | None = "0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sensor_manifests",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(length=10), nullable=False),
        sa.Column("manifest_version", sa.String(length=40), nullable=False),
        sa.Column("profile", sa.String(length=30), nullable=False),
        sa.Column("page_match", sa.String(length=512), nullable=False),
        sa.Column("observations", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'superseded', 'expired')",
            name="ck_sensor_manifests_status",
        ),
        sa.CheckConstraint("expires_at > valid_from", name="ck_sensor_manifests_validity"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("website_id", "manifest_version", name="uq_sensor_manifest_version"),
    )
    op.create_index("ix_sensor_manifests_website_id", "sensor_manifests", ["website_id"])
    op.create_index(
        "ix_sensor_manifests_manifest_version", "sensor_manifests", ["manifest_version"]
    )
    op.create_index("ix_sensor_manifests_status", "sensor_manifests", ["status"])
    op.create_index("ix_sensor_manifests_expires_at", "sensor_manifests", ["expires_at"])

    op.create_table(
        "sensor_outcome_definitions",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("minimum_evidence", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "minimum_evidence IN ('click_proxy', 'thank_you_url', 'success_state', "
            "'data_layer', 'application_event', 'server_confirmed')",
            name="ck_sensor_outcomes_evidence",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'retired')", name="ck_sensor_outcomes_status"
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from",
            name="ck_sensor_outcomes_validity",
        ),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("website_id", "key", "valid_from", name="uq_sensor_outcome_version"),
    )
    op.create_index(
        "ix_sensor_outcome_definitions_website_id", "sensor_outcome_definitions", ["website_id"]
    )
    op.create_index("ix_sensor_outcome_definitions_key", "sensor_outcome_definitions", ["key"])
    op.create_index(
        "ix_sensor_outcome_definitions_status", "sensor_outcome_definitions", ["status"]
    )

    op.create_table(
        "sensor_daily_page_metrics",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("url_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("manifest_version", sa.String(length=40), nullable=False),
        sa.Column("page_sessions", sa.Integer(), nullable=False),
        sa.Column("active_time_buckets", sa.JSON(), nullable=False),
        sa.Column("exposures", sa.Integer(), nullable=False),
        sa.Column("interactions", sa.Integer(), nullable=False),
        sa.Column("process_starts", sa.Integer(), nullable=False),
        sa.Column("observed_outcomes", sa.Integer(), nullable=False),
        sa.Column("trusted_outcomes", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("sampled_count", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "page_sessions >= 0 AND exposures >= 0 AND interactions >= 0 "
            "AND process_starts >= 0 AND observed_outcomes >= 0 AND trusted_outcomes >= 0 "
            "AND rejected_count >= 0 AND sampled_count >= 0",
            name="ck_sensor_daily_metrics_non_negative",
        ),
        sa.ForeignKeyConstraint(["url_id"], ["urls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "website_id", "url_id", "date", "manifest_version", name="uq_sensor_daily_page_metric"
        ),
    )
    op.create_index(
        "ix_sensor_daily_page_metrics_website_id", "sensor_daily_page_metrics", ["website_id"]
    )
    op.create_index("ix_sensor_daily_page_metrics_url_id", "sensor_daily_page_metrics", ["url_id"])
    op.create_index("ix_sensor_daily_page_metrics_date", "sensor_daily_page_metrics", ["date"])
    op.create_index(
        "ix_sensor_daily_page_metrics_manifest_version",
        "sensor_daily_page_metrics",
        ["manifest_version"],
    )

    op.create_table(
        "sensor_measurement_states",
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("client_version", sa.String(length=32), nullable=True),
        sa.Column("schema_version", sa.String(length=10), nullable=True),
        sa.Column("manifest_version", sa.String(length=40), nullable=True),
        sa.Column("first_observation_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_observation_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_pages", sa.Integer(), nullable=False),
        sa.Column("observed_pages", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("sampled_count", sa.Integer(), nullable=False),
        sa.Column("outcome_evidence", sa.JSON(), nullable=False),
        sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('not_configured', 'provisional', 'reliable', 'attention_needed', 'stale')",
            name="ck_sensor_measurement_states_status",
        ),
        sa.CheckConstraint(
            "period_end >= period_start", name="ck_sensor_measurement_states_period"
        ),
        sa.CheckConstraint(
            "expected_pages >= 0 AND observed_pages >= 0 AND rejected_count >= 0 "
            "AND sampled_count >= 0",
            name="ck_sensor_measurement_states_non_negative",
        ),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "website_id", "period_start", "period_end", "input_hash", name="uq_sensor_state_input"
        ),
    )
    op.create_index(
        "ix_sensor_measurement_states_website_id", "sensor_measurement_states", ["website_id"]
    )
    op.create_index(
        "ix_sensor_measurement_states_period_start", "sensor_measurement_states", ["period_start"]
    )
    op.create_index(
        "ix_sensor_measurement_states_period_end", "sensor_measurement_states", ["period_end"]
    )
    op.create_index("ix_sensor_measurement_states_status", "sensor_measurement_states", ["status"])


def downgrade() -> None:
    op.drop_table("sensor_measurement_states")
    op.drop_table("sensor_daily_page_metrics")
    op.drop_table("sensor_outcome_definitions")
    op.drop_table("sensor_manifests")

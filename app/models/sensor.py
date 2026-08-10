import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import UUIDTimestampMixin


class SensorManifest(UUIDTimestampMixin, Base):
    __tablename__ = "sensor_manifests"
    __table_args__ = (
        UniqueConstraint("website_id", "manifest_version", name="uq_sensor_manifest_version"),
        CheckConstraint(
            "status IN ('draft', 'active', 'superseded', 'expired')",
            name="ck_sensor_manifests_status",
        ),
        CheckConstraint("expires_at > valid_from", name="ck_sensor_manifests_validity"),
    )

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    schema_version: Mapped[str] = mapped_column(String(10))
    manifest_version: Mapped[str] = mapped_column(String(40), index=True)
    profile: Mapped[str] = mapped_column(String(30))
    page_match: Mapped[str] = mapped_column(String(512))
    observations: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class SensorOutcomeDefinition(UUIDTimestampMixin, Base):
    __tablename__ = "sensor_outcome_definitions"
    __table_args__ = (
        UniqueConstraint("website_id", "key", "valid_from", name="uq_sensor_outcome_version"),
        CheckConstraint(
            "minimum_evidence IN ('click_proxy', 'thank_you_url', 'success_state', "
            "'data_layer', 'application_event', 'server_confirmed')",
            name="ck_sensor_outcomes_evidence",
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'retired')", name="ck_sensor_outcomes_status"
        ),
        CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from",
            name="ck_sensor_outcomes_validity",
        ),
    )

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(160))
    minimum_evidence: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SensorDailyPageMetric(UUIDTimestampMixin, Base):
    __tablename__ = "sensor_daily_page_metrics"
    __table_args__ = (
        UniqueConstraint(
            "website_id",
            "url_id",
            "date",
            "manifest_version",
            name="uq_sensor_daily_page_metric",
        ),
        CheckConstraint(
            "page_sessions >= 0 AND exposures >= 0 AND interactions >= 0 "
            "AND process_starts >= 0 AND observed_outcomes >= 0 AND trusted_outcomes >= 0 "
            "AND rejected_count >= 0 AND sampled_count >= 0",
            name="ck_sensor_daily_metrics_non_negative",
        ),
    )

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    url_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("urls.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    manifest_version: Mapped[str] = mapped_column(String(40), index=True)
    page_sessions: Mapped[int] = mapped_column(Integer, default=0)
    active_time_buckets: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    exposures: Mapped[int] = mapped_column(Integer, default=0)
    interactions: Mapped[int] = mapped_column(Integer, default=0)
    process_starts: Mapped[int] = mapped_column(Integer, default=0)
    observed_outcomes: Mapped[int] = mapped_column(Integer, default=0)
    trusted_outcomes: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    sampled_count: Mapped[int] = mapped_column(Integer, default=0)


class SensorMeasurementState(UUIDTimestampMixin, Base):
    __tablename__ = "sensor_measurement_states"
    __table_args__ = (
        UniqueConstraint(
            "website_id", "period_start", "period_end", "input_hash", name="uq_sensor_state_input"
        ),
        CheckConstraint(
            "status IN ('not_configured', 'provisional', 'reliable', 'attention_needed', 'stale')",
            name="ck_sensor_measurement_states_status",
        ),
        CheckConstraint("period_end >= period_start", name="ck_sensor_measurement_states_period"),
        CheckConstraint(
            "expected_pages >= 0 AND observed_pages >= 0 AND rejected_count >= 0 "
            "AND sampled_count >= 0",
            name="ck_sensor_measurement_states_non_negative",
        ),
    )

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    period_start: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    client_version: Mapped[str | None] = mapped_column(String(32))
    schema_version: Mapped[str | None] = mapped_column(String(10))
    manifest_version: Mapped[str | None] = mapped_column(String(40))
    first_observation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_observation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expected_pages: Mapped[int] = mapped_column(Integer, default=0)
    observed_pages: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    sampled_count: Mapped[int] = mapped_column(Integer, default=0)
    outcome_evidence: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    checks: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    input_hash: Mapped[str] = mapped_column(String(64))

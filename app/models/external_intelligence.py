import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import UUIDTimestampMixin, utc_now


class ExternalIntelligenceRequest(UUIDTimestampMixin, Base):
    __tablename__ = "external_intelligence_requests"
    __table_args__ = (
        UniqueConstraint(
            "website_id",
            "capability",
            "idempotency_key",
            name="uq_external_request_idempotency",
        ),
        UniqueConstraint("id", "website_id", name="uq_external_request_tenant"),
        CheckConstraint(
            "capability IN ('serp', 'ai_citations')",
            name="ck_external_requests_capability",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_external_requests_status",
        ),
        CheckConstraint(
            "estimated_cost_micros >= 0 AND "
            "(actual_cost_micros IS NULL OR actual_cost_micros >= 0)",
            name="ck_external_requests_costs",
        ),
    )

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    url_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("urls.id", ondelete="SET NULL"), index=True
    )
    capability: Mapped[str] = mapped_column(String(30), index=True)
    cache_key: Mapped[str] = mapped_column(String(512), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    provider: Mapped[str | None] = mapped_column(String(40))
    request_context: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    budget_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    estimated_cost_micros: Mapped[int] = mapped_column(Integer, default=0)
    actual_cost_micros: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))


class ExternalObservation(UUIDTimestampMixin, Base):
    __tablename__ = "external_observations"
    __table_args__ = (
        UniqueConstraint("request_id", "evidence_hash", name="uq_external_observation_evidence"),
        ForeignKeyConstraint(
            ["request_id", "website_id"],
            ["external_intelligence_requests.id", "external_intelligence_requests.website_id"],
            ondelete="CASCADE",
            name="fk_external_observation_request_tenant",
        ),
        CheckConstraint(
            "capability IN ('serp', 'ai_citations')",
            name="ck_external_observations_capability",
        ),
    )

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(index=True)
    capability: Mapped[str] = mapped_column(String(30), index=True)
    cache_key: Mapped[str] = mapped_column(String(512), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    evidence_hash: Mapped[str] = mapped_column(String(64))
    normalized_payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    source_coverage: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class ExternalUsageRecord(Base):
    __tablename__ = "external_usage_records"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_external_usage_request"),
        ForeignKeyConstraint(
            ["request_id", "website_id"],
            ["external_intelligence_requests.id", "external_intelligence_requests.website_id"],
            ondelete="CASCADE",
            name="fk_external_usage_request_tenant",
        ),
        CheckConstraint(
            "capability IN ('serp', 'ai_citations')",
            name="ck_external_usage_capability",
        ),
        CheckConstraint(
            "estimated_cost_micros >= 0 AND actual_cost_micros >= 0 AND units >= 0",
            name="ck_external_usage_values",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(index=True)
    capability: Mapped[str] = mapped_column(String(30), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    units: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_micros: Mapped[int] = mapped_column(Integer, default=0)
    actual_cost_micros: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )

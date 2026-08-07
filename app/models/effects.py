import uuid
from datetime import date, datetime

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import utc_now


class EffectIntervention(Base):
    __tablename__ = "effect_interventions"
    __table_args__ = (
        UniqueConstraint("task_id", name="uq_effect_interventions_task"),
        UniqueConstraint(
            "website_id",
            "input_hash",
            "intervention_version",
            name="uq_effect_interventions_input_version",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recommendation_tasks.id", ondelete="CASCADE"), index=True
    )
    implemented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    intervention_version: Mapped[str] = mapped_column(String(30))
    input_hash: Mapped[str] = mapped_column(String(64))
    task_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    url_context: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    source_coverage: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EffectEvaluation(Base):
    __tablename__ = "effect_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "website_id", "input_hash", "method_version", name="uq_effect_evaluations_input_method"
        ),
        CheckConstraint(
            "status IN ('too_early', 'insufficient_data', 'not_comparable', 'development_visible')",
            name="ck_effect_evaluations_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    change_period_start: Mapped[date] = mapped_column(Date)
    change_period_end: Mapped[date] = mapped_column(Date)
    baseline_start: Mapped[date] = mapped_column(Date)
    baseline_end: Mapped[date] = mapped_column(Date)
    observation_start: Mapped[date] = mapped_column(Date)
    observation_end: Mapped[date] = mapped_column(Date)
    method_version: Mapped[str] = mapped_column(String(30), index=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), index=True)
    analytics_source: Mapped[str | None] = mapped_column(String(20))
    intervention_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    url_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    metrics: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    source_coverage: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    confidence_factors: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import UUIDTimestampMixin


class PerformanceObservation(UUIDTimestampMixin, Base):
    """Immutable, normalized PageSpeed/Lighthouse and CrUX observation."""

    __tablename__ = "performance_observations"

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    url_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("urls.id", ondelete="CASCADE"), index=True
    )
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    strategy: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    source: Mapped[str] = mapped_column(String(40), default="pagespeed_insights")
    requested_url: Mapped[str] = mapped_column(String(2048))
    final_url: Mapped[str | None] = mapped_column(String(2048))
    lighthouse_version: Mapped[str | None] = mapped_column(String(40))
    fetch_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    category_scores: Mapped[dict[str, float | None]] = mapped_column(JSON, default=dict)
    lab_metrics: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    field_metrics: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    origin_field_metrics: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    failed_audits: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    field_scope: Mapped[str | None] = mapped_column(String(30))
    collection_period_days: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)

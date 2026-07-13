import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import UUIDTimestampMixin, utc_now


class JobListing(UUIDTimestampMixin, Base):
    """Current structured state of a vacancy, backed by URL snapshots."""

    __tablename__ = "job_listings"
    __table_args__ = (UniqueConstraint("website_id", "url_id"),)

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    url_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("urls.id", ondelete="CASCADE"), index=True
    )
    latest_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("url_snapshots.id", ondelete="SET NULL"), index=True
    )
    detection_sources: Mapped[list[str]] = mapped_column(JSON, default=list)
    title: Mapped[str | None] = mapped_column(Text)
    employer: Mapped[str | None] = mapped_column(String(512))
    locations: Mapped[list[str]] = mapped_column(JSON, default=list)
    date_posted: Mapped[date | None] = mapped_column(Date)
    valid_through: Mapped[date | None] = mapped_column(Date, index=True)
    salary_data: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    hours: Mapped[str | None] = mapped_column(String(255))
    employment_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    external_identifier: Mapped[str | None] = mapped_column(String(512))
    application_url: Mapped[str | None] = mapped_column(String(2048))
    job_posting_data: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    lifecycle_status: Mapped[str] = mapped_column(String(30), default="new", index=True)
    manual_status: Mapped[str | None] = mapped_column(String(30), index=True)
    current_status_code: Mapped[int | None] = mapped_column(Integer)
    is_indexable: Mapped[bool | None] = mapped_column(Boolean)
    inbound_internal_links: Mapped[int] = mapped_column(Integer, default=0)
    first_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    last_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )

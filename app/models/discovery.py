import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import UUIDTimestampMixin, utc_now


class Url(Base):
    __tablename__ = "urls"
    __table_args__ = (UniqueConstraint("website_id", "normalized_url"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    normalized_url: Mapped[str] = mapped_column(String(2048))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    current_status_code: Mapped[int | None] = mapped_column(Integer)
    current_final_url: Mapped[str | None] = mapped_column(String(2048))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_indexable: Mapped[bool | None] = mapped_column(Boolean)
    is_important: Mapped[bool] = mapped_column(Boolean, default=False)
    page_type: Mapped[str | None] = mapped_column(String(50))
    crawl_depth: Mapped[int | None] = mapped_column(Integer, index=True)
    last_light_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_full_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sources: Mapped[list["UrlSource"]] = relationship(cascade="all, delete-orphan")


class UrlSource(Base):
    __tablename__ = "url_sources"
    __table_args__ = (UniqueConstraint("url_id", "source_type", "source_url"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    url_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("urls.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(30), index=True)
    source_url: Mapped[str] = mapped_column(String(2048), default="")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CrawlJob(UUIDTimestampMixin, Base):
    __tablename__ = "crawl_jobs"

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    job_type: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    settings_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import utc_now


class Change(Base):
    __tablename__ = "changes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    url_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("urls.id", ondelete="CASCADE"), index=True)
    previous_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("url_snapshots.id", ondelete="SET NULL")
    )
    current_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("url_snapshots.id", ondelete="CASCADE"), index=True
    )
    change_type: Mapped[str] = mapped_column(String(50), index=True)
    field_name: Mapped[str | None] = mapped_column(String(100))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (UniqueConstraint("website_id", "url_id", "issue_type"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    url_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("urls.id", ondelete="CASCADE"), index=True
    )
    issue_type: Mapped[str] = mapped_column(String(100), index=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    confidence: Mapped[str] = mapped_column(String(20), default="high")
    status: Mapped[str] = mapped_column(String(30), default="new", index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    recommended_action: Mapped[str] = mapped_column(Text)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_to: Mapped[str | None] = mapped_column(String(255))
    due_date: Mapped[date | None] = mapped_column(Date)


class IssueOccurrence(Base):
    __tablename__ = "issue_occurrences"
    __table_args__ = (UniqueConstraint("issue_id", "crawl_run_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    issue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"), index=True
    )
    crawl_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"), index=True
    )
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("url_snapshots.id", ondelete="SET NULL")
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    evidence: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class IssueComment(Base):
    __tablename__ = "issue_comments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    issue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"), index=True
    )
    author: Mapped[str] = mapped_column(String(255))
    comment: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IssueSuppression(Base):
    __tablename__ = "issue_suppressions"
    __table_args__ = (UniqueConstraint("website_id", "url_id", "issue_type"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    url_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("urls.id", ondelete="CASCADE"), index=True)
    issue_type: Mapped[str] = mapped_column(String(100), index=True)
    actor: Mapped[str | None] = mapped_column(String(320))
    comment: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    restored_by: Mapped[str | None] = mapped_column(String(320))


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    actor: Mapped[str | None] = mapped_column(String(320))
    activity_type: Mapped[str] = mapped_column(String(80), index=True)
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )

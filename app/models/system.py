import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import UUIDTimestampMixin


class CrawlDeploymentControl(Base):
    """Singleton containing the durable global crawl deployment drain."""

    __tablename__ = "crawl_deployment_control"
    __table_args__ = (CheckConstraint("id = 1", name="ck_crawl_deployment_control_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    paused_job_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RetentionOperation(UUIDTimestampMixin, Base):
    """Durable, resumable retention for one dataset after a completed crawl."""

    __tablename__ = "retention_operations"
    __table_args__ = (
        UniqueConstraint(
            "trigger_crawl_run_id",
            "dataset",
            name="uq_retention_operations_trigger_dataset",
        ),
    )

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    trigger_crawl_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"), index=True
    )
    dataset: Mapped[str] = mapped_column(String(80), default="element_locations", index=True)
    policy_version: Mapped[str] = mapped_column(String(40), default="2026-08-02-v1")
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    rows_deleted: Mapped[int] = mapped_column(Integer, default=0)
    batches_completed: Mapped[int] = mapped_column(Integer, default=0)
    candidates_remaining: Mapped[int | None] = mapped_column(Integer)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    before_report: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    after_report: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)

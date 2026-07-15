from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CrawlDeploymentControl(Base):
    """Singleton containing the durable global crawl deployment drain."""

    __tablename__ = "crawl_deployment_control"
    __table_args__ = (CheckConstraint("id = 1", name="ck_crawl_deployment_control_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    paused_job_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

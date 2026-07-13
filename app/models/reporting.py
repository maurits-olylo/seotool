import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import UUIDTimestampMixin


class MonthlyReportSnapshot(UUIDTimestampMixin, Base):
    __tablename__ = "monthly_report_snapshots"
    __table_args__ = (UniqueConstraint("website_id", "period_start"),)

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    period_start: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date] = mapped_column(Date)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    report_data: Mapped[dict[str, object]] = mapped_column(JSON)

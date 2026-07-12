import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import utc_now


class Export(Base):
    __tablename__ = "exports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    export_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    file_path: Mapped[str | None] = mapped_column(String(2048))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

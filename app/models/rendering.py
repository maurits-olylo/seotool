import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import UUIDTimestampMixin


class RenderObservation(UUIDTimestampMixin, Base):
    __tablename__ = "render_observations"
    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    url_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("urls.id", ondelete="CASCADE"), index=True
    )
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("url_snapshots.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    trigger_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    rendered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    browser_name: Mapped[str | None] = mapped_column(String(80))
    rendered_word_count: Mapped[int | None] = mapped_column(Integer)
    rendered_main_content_hash: Mapped[str | None] = mapped_column(String(64))
    rendered_metadata_hash: Mapped[str | None] = mapped_column(String(64))
    rendered_links_hash: Mapped[str | None] = mapped_column(String(64))
    rendered_schema_hash: Mapped[str | None] = mapped_column(String(64))
    screenshot_key: Mapped[str | None] = mapped_column(String(255), unique=True)
    screenshot_sha256: Mapped[str | None] = mapped_column(String(64))
    screenshot_bytes: Mapped[int | None] = mapped_column(BigInteger)
    screenshot_width: Mapped[int | None] = mapped_column(Integer)
    screenshot_height: Mapped[int | None] = mapped_column(Integer)
    screenshot_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comparison: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)

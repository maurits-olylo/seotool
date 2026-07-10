import uuid

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import UUIDTimestampMixin


class Website(UUIDTimestampMixin, Base):
    __tablename__ = "websites"
    __table_args__ = (UniqueConstraint("client_id", "base_url"),)

    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    base_url: Mapped[str] = mapped_column(String(2048))
    language: Mapped[str | None] = mapped_column(String(10))
    country: Mapped[str | None] = mapped_column(String(2))
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    client: Mapped["Client"] = relationship(back_populates="websites")  # noqa: F821
    settings: Mapped["WebsiteSettings"] = relationship(cascade="all, delete-orphan", uselist=False)


class WebsiteSettings(Base):
    __tablename__ = "website_settings"

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), primary_key=True
    )
    sitemap_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_subdomains: Mapped[list[str]] = mapped_column(JSON, default=list)
    excluded_url_patterns: Mapped[list[str]] = mapped_column(JSON, default=list)
    ignored_query_parameters: Mapped[list[str]] = mapped_column(JSON, default=list)
    max_urls: Mapped[int] = mapped_column(Integer, default=10_000)
    request_delay_ms: Mapped[int] = mapped_column(Integer, default=200)
    concurrency: Mapped[int] = mapped_column(Integer, default=5)
    request_timeout_seconds: Mapped[int] = mapped_column(Integer, default=20)
    max_response_size: Mapped[int] = mapped_column(Integer, default=5_000_000)
    respect_robots_txt: Mapped[bool] = mapped_column(Boolean, default=True)
    light_check_interval: Mapped[str] = mapped_column(Text, default="daily")
    full_crawl_interval: Mapped[str] = mapped_column(Text, default="weekly")

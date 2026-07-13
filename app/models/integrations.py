import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import UUIDTimestampMixin


class IntegrationConnection(UUIDTimestampMixin, Base):
    __tablename__ = "integration_connections"
    __table_args__ = (UniqueConstraint("client_id", "provider"),)

    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(30), index=True)
    account_email: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    encrypted_access_token: Mapped[str | None] = mapped_column(Text)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class WebsiteIntegration(UUIDTimestampMixin, Base):
    __tablename__ = "website_integrations"
    __table_args__ = (UniqueConstraint("website_id", "service"),)

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integration_connections.id", ondelete="CASCADE"), index=True
    )
    service: Mapped[str] = mapped_column(String(40), index=True)
    external_property_id: Mapped[str] = mapped_column(String(512))
    external_property_name: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settings: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class SearchConsoleMetric(UUIDTimestampMixin, Base):
    __tablename__ = "search_console_metrics"
    __table_args__ = (UniqueConstraint("website_id", "date", "page_url"),)

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    url_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("urls.id", ondelete="SET NULL"), index=True
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    page_url: Mapped[str] = mapped_column(String(2048))
    clicks: Mapped[float] = mapped_column(Float, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    ctr: Mapped[float] = mapped_column(Float, default=0)
    position: Mapped[float] = mapped_column(Float, default=0)


class SearchConsoleQueryMetric(UUIDTimestampMixin, Base):
    """Daily Google Search Console performance by query and landing page."""

    __tablename__ = "search_console_query_metrics"
    __table_args__ = (UniqueConstraint("website_id", "date", "query", "page_url"),)

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    url_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("urls.id", ondelete="SET NULL"), index=True
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    query: Mapped[str] = mapped_column(String(2048), index=True)
    page_url: Mapped[str] = mapped_column(String(2048))
    clicks: Mapped[float] = mapped_column(Float, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    ctr: Mapped[float] = mapped_column(Float, default=0)
    position: Mapped[float] = mapped_column(Float, default=0)


class GoogleAnalyticsMetric(UUIDTimestampMixin, Base):
    __tablename__ = "google_analytics_metrics"
    __table_args__ = (UniqueConstraint("website_id", "date", "landing_page"),)

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    url_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("urls.id", ondelete="SET NULL"), index=True
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    landing_page: Mapped[str] = mapped_column(String(2048))
    sessions: Mapped[int] = mapped_column(Integer, default=0)
    active_users: Mapped[int] = mapped_column(Integer, default=0)
    key_events: Mapped[float] = mapped_column(Float, default=0)


class GoogleAnalyticsEventMetric(UUIDTimestampMixin, Base):
    __tablename__ = "google_analytics_event_metrics"
    __table_args__ = (UniqueConstraint("website_id", "date", "event_name"),)

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    event_name: Mapped[str] = mapped_column(String(255), index=True)
    key_events: Mapped[float] = mapped_column(Float, default=0)

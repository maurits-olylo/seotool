import uuid
from datetime import date, datetime
from hashlib import sha256
from typing import Any, Protocol

from sqlalchemy import (
    JSON,
    Boolean,
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


class _ColumnDefaultContext(Protocol):
    def get_current_parameters(self) -> dict[str, Any]: ...


def _page_metric_dedup_key(context: _ColumnDefaultContext) -> str:
    page_url = str(context.get_current_parameters()["page_url"])
    return sha256(page_url.encode("utf-8")).hexdigest()


def _query_metric_dedup_key(context: _ColumnDefaultContext) -> str:
    parameters = context.get_current_parameters()
    query = str(parameters["query"])
    page_url = str(parameters["page_url"])
    return sha256(f"{query}\0{page_url}".encode()).hexdigest()


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
    settings: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
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


class UrlInspectionResult(UUIDTimestampMixin, Base):
    """Immutable Google URL Inspection observation for one registered URL."""

    __tablename__ = "url_inspection_results"

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    url_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("urls.id", ondelete="CASCADE"), index=True)
    inspected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    inspection_result_link: Mapped[str | None] = mapped_column(String(2048))
    verdict: Mapped[str | None] = mapped_column(String(40), index=True)
    coverage_state: Mapped[str | None] = mapped_column(String(255))
    indexing_state: Mapped[str | None] = mapped_column(String(80))
    page_fetch_state: Mapped[str | None] = mapped_column(String(80))
    robots_txt_state: Mapped[str | None] = mapped_column(String(80))
    last_crawl_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    google_canonical: Mapped[str | None] = mapped_column(String(2048))
    user_canonical: Mapped[str | None] = mapped_column(String(2048))
    referring_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    sitemap_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    rich_results: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    raw_response: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class SearchConsoleMetric(UUIDTimestampMixin, Base):
    __tablename__ = "search_console_metrics"
    __table_args__ = (
        UniqueConstraint(
            "website_id",
            "date",
            "dedup_key",
            name="uq_search_console_metrics_website_date_dedup",
        ),
    )

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    url_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("urls.id", ondelete="SET NULL"), index=True
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    page_url: Mapped[str] = mapped_column(String(2048))
    dedup_key: Mapped[str] = mapped_column(String(64), default=_page_metric_dedup_key)
    clicks: Mapped[float] = mapped_column(Float, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    ctr: Mapped[float] = mapped_column(Float, default=0)
    position: Mapped[float] = mapped_column(Float, default=0)


class SearchConsoleQueryMetric(UUIDTimestampMixin, Base):
    """Daily Google Search Console performance by query and landing page."""

    __tablename__ = "search_console_query_metrics"
    __table_args__ = (
        UniqueConstraint(
            "website_id",
            "date",
            "dedup_key",
            name="uq_search_console_query_metrics_website_date_dedup",
        ),
    )

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    url_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("urls.id", ondelete="SET NULL"), index=True
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    query: Mapped[str] = mapped_column(String(2048))
    page_url: Mapped[str] = mapped_column(String(2048))
    dedup_key: Mapped[str] = mapped_column(String(64), default=_query_metric_dedup_key)
    clicks: Mapped[float] = mapped_column(Float, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    ctr: Mapped[float] = mapped_column(Float, default=0)
    position: Mapped[float] = mapped_column(Float, default=0)


class BingPageMetric(UUIDTimestampMixin, Base):
    __tablename__ = "bing_page_metrics"
    __table_args__ = (UniqueConstraint("website_id", "date", "page_url"),)

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    url_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("urls.id", ondelete="SET NULL"), index=True
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    page_url: Mapped[str] = mapped_column(String(2048))
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    average_click_position: Mapped[float] = mapped_column(Float, default=0)
    average_impression_position: Mapped[float] = mapped_column(Float, default=0)


class BingQueryMetric(UUIDTimestampMixin, Base):
    __tablename__ = "bing_query_metrics"
    __table_args__ = (UniqueConstraint("website_id", "date", "query"),)

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    query: Mapped[str] = mapped_column(String(2048))
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    average_click_position: Mapped[float] = mapped_column(Float, default=0)
    average_impression_position: Mapped[float] = mapped_column(Float, default=0)


class BingLinkTarget(UUIDTimestampMixin, Base):
    __tablename__ = "bing_link_targets"
    __table_args__ = (UniqueConstraint("website_id", "target_url"),)

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    url_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("urls.id", ondelete="SET NULL"), index=True
    )
    target_url: Mapped[str] = mapped_column(String(2048))
    inbound_link_count: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class BingInboundLink(UUIDTimestampMixin, Base):
    __tablename__ = "bing_inbound_links"
    __table_args__ = (UniqueConstraint("website_id", "link_key"),)

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    link_key: Mapped[str] = mapped_column(String(64))
    target_url: Mapped[str] = mapped_column(String(2048), index=True)
    source_url: Mapped[str] = mapped_column(String(2048))
    anchor_text: Mapped[str] = mapped_column(Text, default="")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class BingReferringDomain(UUIDTimestampMixin, Base):
    __tablename__ = "bing_referring_domains"
    __table_args__ = (UniqueConstraint("website_id", "domain"),)

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    domain: Mapped[str] = mapped_column(String(2048))
    backlink_count: Mapped[int] = mapped_column(Integer, default=0)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class BingReferringAnchor(UUIDTimestampMixin, Base):
    __tablename__ = "bing_referring_anchors"
    __table_args__ = (UniqueConstraint("website_id", "anchor_key"),)

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    anchor_key: Mapped[str] = mapped_column(String(64))
    anchor_text: Mapped[str] = mapped_column(Text)
    backlink_count: Mapped[int] = mapped_column(Integer, default=0)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


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


class GoogleAnalyticsLandingPageEventMetric(UUIDTimestampMixin, Base):
    """Daily organic GA4 key events by landing page and event name."""

    __tablename__ = "google_analytics_landing_page_event_metrics"
    __table_args__ = (UniqueConstraint("website_id", "date", "landing_page", "event_name"),)

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    url_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("urls.id", ondelete="SET NULL"), index=True
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    landing_page: Mapped[str] = mapped_column(String(2048))
    event_name: Mapped[str] = mapped_column(String(255), index=True)
    key_events: Mapped[float] = mapped_column(Float, default=0)


class MatomoPageMetric(UUIDTimestampMixin, Base):
    __tablename__ = "matomo_page_metrics"
    __table_args__ = (UniqueConstraint("website_id", "date", "page_url"),)

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    url_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("urls.id", ondelete="SET NULL"), index=True
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    page_url: Mapped[str] = mapped_column(String(2048))
    visits: Mapped[int] = mapped_column(Integer, default=0)
    pageviews: Mapped[int] = mapped_column(Integer, default=0)
    unique_pageviews: Mapped[int] = mapped_column(Integer, default=0)
    entry_visits: Mapped[int] = mapped_column(Integer, default=0)
    bounces: Mapped[int] = mapped_column(Integer, default=0)
    exits: Mapped[int] = mapped_column(Integer, default=0)
    conversions: Mapped[float] = mapped_column(Float, default=0)


class MatomoAggregateMetric(UUIDTimestampMixin, Base):
    __tablename__ = "matomo_aggregate_metrics"
    __table_args__ = (UniqueConstraint("website_id", "date", "metric_type", "dimension_key"),)

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    metric_type: Mapped[str] = mapped_column(String(40), index=True)
    dimension_key: Mapped[str] = mapped_column(String(512))
    dimension_name: Mapped[str] = mapped_column(String(512))
    visits: Mapped[int] = mapped_column(Integer, default=0)
    actions: Mapped[int] = mapped_column(Integer, default=0)
    conversions: Mapped[float] = mapped_column(Float, default=0)
    revenue: Mapped[float] = mapped_column(Float, default=0)

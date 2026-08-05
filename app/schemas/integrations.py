from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Timestamped

Provider = Literal["google", "bing"]
Service = Literal["search_console", "ga4", "bing_webmaster", "matomo"]


class IntegrationConnectionCreate(BaseModel):
    provider: Provider
    account_email: str | None = None


class IntegrationConnectionRead(Timestamped):
    client_id: UUID
    provider: str
    account_email: str | None
    status: str
    scopes: list[str]
    settings: dict[str, object]
    last_synced_at: datetime | None
    last_error: str | None


class WebsiteIntegrationCreate(BaseModel):
    connection_id: UUID
    service: Service
    external_property_id: str = Field(min_length=1, max_length=512)
    external_property_name: str | None = Field(default=None, max_length=512)


class WebsiteIntegrationRead(Timestamped):
    website_id: UUID
    connection_id: UUID
    service: str
    external_property_id: str
    external_property_name: str | None
    status: str
    last_synced_at: datetime | None
    settings: dict[str, object]


class WebsiteIntegrationUpsert(BaseModel):
    connection_id: UUID
    external_property_id: str = Field(min_length=1, max_length=512)
    external_property_name: str | None = Field(default=None, max_length=512)


class UrlInspectionResultRead(Timestamped):
    website_id: UUID
    url_id: UUID
    inspected_at: datetime
    inspection_result_link: str | None
    verdict: str | None
    coverage_state: str | None
    indexing_state: str | None
    page_fetch_state: str | None
    robots_txt_state: str | None
    last_crawl_time: datetime | None
    google_canonical: str | None
    user_canonical: str | None
    referring_urls: list[str]
    sitemap_urls: list[str]
    rich_results: dict[str, object]


class PerformanceObservationRead(Timestamped):
    website_id: UUID
    url_id: UUID
    analyzed_at: datetime
    strategy: str
    status: str
    source: str
    requested_url: str
    final_url: str | None
    lighthouse_version: str | None
    fetch_time: datetime | None
    category_scores: dict[str, float | None]
    lab_metrics: dict[str, object]
    field_metrics: dict[str, object]
    origin_field_metrics: dict[str, object]
    failed_audits: list[dict[str, object]]
    field_scope: str | None
    collection_period_days: int | None
    error_code: str | None
    error_message: str | None


class GoogleProperty(BaseModel):
    id: str
    name: str
    permission: str | None = None
    account: str | None = None


class GooglePropertiesRead(BaseModel):
    search_console: list[GoogleProperty]
    ga4: list[GoogleProperty]


class BingProperty(BaseModel):
    id: str
    name: str
    verified: bool


class BingPropertiesRead(BaseModel):
    sites: list[BingProperty]


class MatomoConnectionCreate(BaseModel):
    server_url: str = Field(min_length=8, max_length=2048)
    token_auth: str = Field(min_length=1, max_length=512)


class MatomoSite(BaseModel):
    id: str
    name: str
    main_url: str | None = None


class MatomoSitesRead(BaseModel):
    sites: list[MatomoSite]


class PrimaryAnalyticsSourceUpdate(BaseModel):
    source: Literal["ga4", "matomo"]


class BingBacklinkCsvImport(BaseModel):
    domains_csv: str = Field(min_length=1, max_length=2_000_000)
    pages_csv: str = Field(min_length=1, max_length=20_000_000)
    anchors_csv: str = Field(min_length=1, max_length=4_000_000)


class GoogleAnalyticsKeyEventRead(BaseModel):
    event_name: str
    key_events: float
    selected: bool


class GoogleAnalyticsKeyEventSelection(BaseModel):
    event_names: list[str] = Field(default_factory=list, max_length=40)

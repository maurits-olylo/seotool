from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Timestamped

Provider = Literal["google", "bing"]
Service = Literal["search_console", "ga4", "bing_webmaster"]


class IntegrationConnectionCreate(BaseModel):
    provider: Provider
    account_email: str | None = None


class IntegrationConnectionRead(Timestamped):
    client_id: UUID
    provider: str
    account_email: str | None
    status: str
    scopes: list[str]
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

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

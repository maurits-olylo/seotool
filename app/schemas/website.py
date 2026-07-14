from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, Field

from app.schemas.common import ORMModel, Timestamped


class WebsiteCreate(BaseModel):
    client_id: UUID
    name: str = Field(min_length=1, max_length=255)
    base_url: AnyHttpUrl
    language: str | None = None
    country: str | None = Field(default=None, min_length=2, max_length=2)
    status: str = "active"


class WebsiteUpdate(BaseModel):
    name: str | None = None
    base_url: AnyHttpUrl | None = None
    language: str | None = None
    country: str | None = None
    status: str | None = None


class WebsiteRead(Timestamped):
    client_id: UUID
    name: str
    base_url: str
    language: str | None
    country: str | None
    status: str


class WebsiteSettingsData(ORMModel):
    website_id: UUID | None = None
    sitemap_urls: list[str] = Field(default_factory=list)
    allowed_subdomains: list[str] = Field(default_factory=list)
    excluded_url_patterns: list[str] = Field(default_factory=list)
    ignored_query_parameters: list[str] = Field(default_factory=list)
    max_urls: int = Field(default=10_000, ge=1)
    request_delay_ms: int = Field(default=200, ge=0)
    concurrency: int = Field(default=5, ge=1, le=50)
    request_timeout_seconds: int = Field(default=20, ge=1)
    max_response_size: int = Field(default=5_000_000, ge=1)
    respect_robots_txt: bool = True
    light_check_interval: str = "daily"
    full_crawl_interval: str = "weekly"

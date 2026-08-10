from datetime import datetime
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator, model_validator

from app.schemas.website import WebsiteSettingsData


class WebsiteOnboardingStart(BaseModel):
    request_id: UUID
    website_name: str = Field(min_length=1, max_length=255)
    base_url: AnyHttpUrl
    language: str | None = Field(default=None, max_length=10)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    settings: WebsiteSettingsData = Field(default_factory=WebsiteSettingsData)

    @field_validator("website_name")
    @classmethod
    def normalize_website_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Websitenaam is verplicht")
        return value

    @field_validator("base_url")
    @classmethod
    def require_https(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.scheme != "https":
            raise ValueError("Websiteverificatie vereist HTTPS")
        return value


class WebsiteOnboardingRead(BaseModel):
    id: UUID
    client_id: UUID
    website_id: UUID
    status: str
    current_step: str
    last_error_code: str | None
    verification_status: str
    verification_path: str
    verification_expires_at: datetime
    verification_file_content: str | None = None
    first_crawl_job_id: UUID | None = None
    first_crawl_status: str | None = None
    first_crawl_phase: str | None = None
    first_crawl_current: int = 0
    first_crawl_total: int = 0
    first_crawl_discovered_urls: int = 0
    first_crawl_crawled_urls: int = 0
    first_crawl_failed_urls: int = 0
    first_crawl_error: str | None = None
    analytics_quality_status: str = "not_configured"
    analytics_quality_source: str | None = None
    analytics_quality_source_label: str | None = None
    analytics_quality_last_checked_at: datetime | None = None
    conversion_insights_reliable: bool = False


class WebsiteVerificationCheckRead(BaseModel):
    onboarding_id: UUID
    status: str
    current_step: str
    verification_status: str
    attempt_count: int
    last_error_code: str | None


class WebsiteOnboardingCrawlPreferences(BaseModel):
    sitemap_urls: list[str] | None = Field(default=None, max_length=20)
    max_urls: int = Field(default=1_000, ge=1, le=100_000)
    request_delay_ms: int = Field(default=300, ge=100, le=5_000)
    concurrency: int = Field(default=3, ge=1, le=10)
    respect_robots_txt: bool = True

    @model_validator(mode="after")
    def require_safe_robots_setting(self) -> "WebsiteOnboardingCrawlPreferences":
        if not self.respect_robots_txt:
            raise ValueError("Robots.txt respecteren is verplicht tijdens onboarding")
        return self


class WebsiteOnboardingFirstCrawlRead(BaseModel):
    onboarding_id: UUID
    website_id: UUID
    crawl_job_id: UUID
    status: str
    current_step: str
    queue_status: str

from datetime import datetime
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator

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


class WebsiteVerificationCheckRead(BaseModel):
    onboarding_id: UUID
    status: str
    current_step: str
    verification_status: str
    attempt_count: int
    last_error_code: str | None

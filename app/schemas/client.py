from pydantic import AnyHttpUrl, BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel, Timestamped
from app.schemas.website import WebsiteRead


class ClientCreate(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    contact_name: str | None = None
    contact_email: EmailStr | None = None
    internal_reference: str | None = None
    status: str = "active"
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str:
        if value is None or not value.strip():
            raise ValueError("Klantnaam is verplicht")
        return value.strip()

    @field_validator("internal_reference", mode="before")
    @classmethod
    def normalize_internal_reference(cls, value: object) -> object:
        return value.strip() or None if isinstance(value, str) else value


class ClientUpdate(ClientCreate):
    name: str | None = Field(default=None, min_length=1, max_length=255)


class ClientRead(ClientCreate, Timestamped):
    pass


class ClientOnboardingCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    internal_reference: str | None = Field(default=None, max_length=100)
    website_name: str = Field(min_length=1, max_length=255)
    base_url: AnyHttpUrl

    @field_validator("name", "website_name")
    @classmethod
    def normalize_required_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Naam is verplicht")
        return value

    @field_validator("internal_reference", mode="before")
    @classmethod
    def normalize_reference(cls, value: object) -> object:
        return value.strip() or None if isinstance(value, str) else value


class ClientOnboardingRead(BaseModel):
    client: ClientRead
    website: WebsiteRead

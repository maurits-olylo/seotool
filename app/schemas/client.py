from pydantic import EmailStr, Field

from app.schemas.common import ORMModel, Timestamped


class ClientCreate(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    contact_name: str | None = None
    contact_email: EmailStr | None = None
    internal_reference: str | None = None
    status: str = "active"
    notes: str | None = None


class ClientUpdate(ClientCreate):
    name: str | None = Field(default=None, min_length=1, max_length=255)


class ClientRead(ClientCreate, Timestamped):
    pass

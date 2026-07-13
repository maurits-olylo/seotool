import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class MembershipRead(BaseModel):
    client_id: UUID
    role: str


class CurrentUserRead(BaseModel):
    id: UUID | None
    email: str | None
    display_name: str | None
    role: str
    memberships: list[MembershipRead]


class InvitationCreate(BaseModel):
    email: EmailStr
    client_id: UUID
    role: str = Field(pattern="^(admin|user|client)$")


class InvitationRead(BaseModel):
    id: UUID
    email: str
    client_id: UUID
    role: str
    accept_path: str


class InvitationAccept(BaseModel):
    password: str = Field(min_length=12, max_length=256)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        requirements = (
            (r"[a-z]", "een kleine letter"),
            (r"[A-Z]", "een hoofdletter"),
            (r"[0-9]", "een cijfer"),
            (r"[^A-Za-z0-9]", "een speciaal teken"),
        )
        missing = [label for pattern, label in requirements if not re.search(pattern, value)]
        if missing:
            raise ValueError(f"Wachtwoord mist: {', '.join(missing)}")
        return value


class InvitationPreview(BaseModel):
    email: EmailStr
    role: str
    expires_at: datetime


class ClientMemberRead(BaseModel):
    id: UUID
    email: str
    display_name: str | None
    global_role: str
    client_role: str
    is_active: bool


class ClientMemberUpdate(BaseModel):
    role: str = Field(pattern="^(admin|user|client)$")

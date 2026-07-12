from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


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
    display_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=12, max_length=256)


class ClientMemberRead(BaseModel):
    id: UUID
    email: str
    display_name: str | None
    global_role: str
    client_role: str
    is_active: bool

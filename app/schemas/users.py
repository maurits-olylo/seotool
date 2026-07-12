from uuid import UUID

from pydantic import BaseModel


class MembershipRead(BaseModel):
    client_id: UUID
    role: str


class CurrentUserRead(BaseModel):
    id: UUID | None
    email: str | None
    display_name: str | None
    role: str
    memberships: list[MembershipRead]

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal
from app.models.user import ClientMembership
from app.models.website import Website


def accessible_client_ids(db: Session, principal: Principal) -> list[UUID] | None:
    if principal.role == "superuser" or principal.is_api_key:
        return None
    if not principal.user_id:
        return []
    return list(
        db.scalars(
            select(ClientMembership.client_id).where(ClientMembership.user_id == principal.user_id)
        )
    )


def require_client_access(
    db: Session, principal: Principal, client_id: UUID, *, admin: bool = False
) -> ClientMembership | None:
    if principal.role == "superuser" or principal.is_api_key:
        return None
    if not principal.user_id:
        raise HTTPException(status_code=403, detail="No access to this client")
    membership = db.scalar(
        select(ClientMembership).where(
            ClientMembership.user_id == principal.user_id,
            ClientMembership.client_id == client_id,
        )
    )
    if not membership or (admin and membership.role != "admin"):
        raise HTTPException(status_code=403, detail="No access to this client")
    return membership


def require_global_role(principal: Principal, *roles: str) -> None:
    if principal.is_api_key or principal.role in roles:
        return
    raise HTTPException(status_code=403, detail="Insufficient permissions")


def require_website_access(
    db: Session, principal: Principal, website_id: UUID, *, admin: bool = False
) -> Website:
    website = db.get(Website, website_id)
    if not website:
        raise HTTPException(status_code=404, detail="Website not found")
    require_client_access(db, principal, website.client_id, admin=admin)
    return website

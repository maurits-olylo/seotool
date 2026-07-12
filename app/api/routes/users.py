import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import Principal, hash_password, require_api_key
from app.db.session import get_db
from app.models.user import ClientMembership, User, UserInvitation
from app.schemas.users import (
    ClientMemberRead,
    CurrentUserRead,
    InvitationAccept,
    InvitationCreate,
    InvitationRead,
)
from app.services.authorization import require_client_access

router = APIRouter(tags=["users"])
public_router = APIRouter(tags=["users"])


@router.get("/me", response_model=CurrentUserRead)
def current_user(
    principal: Principal = Depends(require_api_key), db: Session = Depends(get_db)
) -> dict[str, object]:
    user = db.get(User, principal.user_id) if principal.user_id else None
    memberships = (
        list(
            db.scalars(
                select(ClientMembership).where(ClientMembership.user_id == principal.user_id)
            )
        )
        if principal.user_id
        else []
    )
    return {
        "id": principal.user_id,
        "email": user.email if user else None,
        "display_name": user.display_name if user else None,
        "role": principal.role,
        "memberships": [
            {"client_id": membership.client_id, "role": membership.role}
            for membership in memberships
        ],
    }


@router.post("/invitations", response_model=InvitationRead, status_code=status.HTTP_201_CREATED)
def create_invitation(
    payload: InvitationCreate,
    principal: Principal = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    require_client_access(db, principal, payload.client_id, admin=True)
    if principal.role == "admin" and payload.role not in {"user", "client"}:
        raise HTTPException(status_code=403, detail="Admins cannot invite other admins")
    if not principal.user_id:
        raise HTTPException(status_code=422, detail="A personal account is required")
    email = payload.email.strip().lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(status_code=409, detail="User already exists")
    token = secrets.token_urlsafe(32)
    invitation = UserInvitation(
        email=email,
        client_id=payload.client_id,
        role=payload.role,
        invited_by_user_id=principal.user_id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return {
        "id": invitation.id,
        "email": invitation.email,
        "client_id": invitation.client_id,
        "role": invitation.role,
        "accept_path": f"/uitnodiging?token={token}",
    }


@router.get("/clients/{client_id}/members", response_model=list[ClientMemberRead])
def list_client_members(
    client_id: UUID,
    principal: Principal = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    require_client_access(db, principal, client_id, admin=True)
    rows = db.execute(
        select(User, ClientMembership)
        .join(ClientMembership, ClientMembership.user_id == User.id)
        .where(ClientMembership.client_id == client_id)
        .order_by(User.email)
    )
    return [
        {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "global_role": user.role,
            "client_role": membership.role,
            "is_active": user.is_active,
        }
        for user, membership in rows
    ]


@public_router.post("/invitations/{token}/accept", status_code=status.HTTP_204_NO_CONTENT)
def accept_invitation(token: str, payload: InvitationAccept, db: Session = Depends(get_db)) -> None:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    invitation = db.scalar(select(UserInvitation).where(UserInvitation.token_hash == token_hash))
    now = datetime.now(UTC)
    expires_at = invitation.expires_at if invitation else None
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if not invitation or invitation.accepted_at or not expires_at or expires_at <= now:
        raise HTTPException(status_code=410, detail="Invitation is invalid or expired")
    user = User(
        email=invitation.email,
        display_name=payload.display_name,
        role=invitation.role,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.flush()
    db.add(ClientMembership(user_id=user.id, client_id=invitation.client_id, role=invitation.role))
    invitation.accepted_at = now
    db.commit()

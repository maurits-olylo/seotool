import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    Principal,
    create_session_token,
    hash_password,
    require_api_key,
    revoke_user_sessions,
    session_user_id,
    verify_password,
)
from app.db.session import get_db
from app.models.user import ClientMembership, User, UserInvitation
from app.schemas.users import (
    ClientMemberRead,
    ClientMemberUpdate,
    CurrentUserRead,
    InvitationAccept,
    InvitationCreate,
    InvitationPreview,
    InvitationRead,
    MfaConfirm,
    MfaSetupRead,
)
from app.services.authorization import require_client_access
from app.services.mfa import (
    generate_recovery_codes,
    generate_totp_secret,
    recovery_code_hash,
    valid_totp_counter,
)
from app.services.oauth import decrypt_token, encrypt_token
from app.services.security_audit import record_security_event

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
        "mfa_enabled": bool(user and user.mfa_enabled),
        "mfa_required": bool(
            user
            and not user.mfa_enabled
            and (
                user.role in {"superuser", "admin"}
                or any(membership.role == "admin" for membership in memberships)
            )
        ),
    }


@router.post("/me/mfa/setup", response_model=MfaSetupRead)
def setup_mfa(
    principal: Principal = Depends(require_api_key), db: Session = Depends(get_db)
) -> dict[str, object]:
    user = db.get(User, principal.user_id) if principal.user_id else None
    if not user:
        raise HTTPException(status_code=403, detail="Een persoonlijke sessie is vereist")
    secret = generate_totp_secret()
    recovery_codes = generate_recovery_codes()
    user.mfa_secret_encrypted = encrypt_token(secret)
    user.mfa_recovery_code_hashes = [recovery_code_hash(code) for code in recovery_codes]
    user.mfa_enabled = False
    user.mfa_last_counter = None
    record_security_event(
        db,
        event_type="mfa.setup_started",
        result="succeeded",
        summary="MFA-instelling gestart",
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
    )
    db.commit()
    label = quote(user.email)
    issuer = quote("SEO Monitor")
    return {
        "secret": secret,
        "provisioning_uri": f"otpauth://totp/SEO%20Monitor:{label}?secret={secret}&issuer={issuer}",
        "recovery_codes": recovery_codes,
    }


@router.post("/me/mfa/confirm", status_code=204)
def confirm_mfa(
    payload: MfaConfirm,
    principal: Principal = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> Response:
    user = db.get(User, principal.user_id) if principal.user_id else None
    if not user or not user.mfa_secret_encrypted:
        raise HTTPException(status_code=409, detail="Start eerst MFA-instelling")
    counter = valid_totp_counter(
        decrypt_token(user.mfa_secret_encrypted) or "",
        payload.code,
        last_counter=user.mfa_last_counter,
    )
    if counter is None:
        raise HTTPException(status_code=422, detail="De verificatiecode is ongeldig")
    user.mfa_enabled = True
    user.mfa_last_counter = counter
    record_security_event(
        db,
        event_type="mfa.enabled",
        result="succeeded",
        summary="MFA geactiveerd",
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
    )
    db.commit()
    return Response(status_code=204)


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
    existing_user = db.scalar(select(User).where(func.lower(User.email) == email))
    if existing_user and db.scalar(
        select(ClientMembership.id).where(
            ClientMembership.user_id == existing_user.id,
            ClientMembership.client_id == payload.client_id,
        )
    ):
        raise HTTPException(status_code=409, detail="Gebruiker heeft al toegang tot deze klant")
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
    db.flush()
    record_security_event(
        db,
        event_type="invitation.created",
        result="succeeded",
        summary="Gebruikersuitnodiging aangemaakt",
        actor_user_id=principal.user_id,
        client_id=payload.client_id,
        target_type="invitation",
        target_id=invitation.id,
        details={"role": payload.role},
    )
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


def _sync_global_role(db: Session, user: User) -> None:
    roles = set(
        db.scalars(select(ClientMembership.role).where(ClientMembership.user_id == user.id))
    )
    user.is_active = bool(roles)
    if "admin" in roles:
        user.role = "admin"
    elif "user" in roles:
        user.role = "user"
    elif "client" in roles:
        user.role = "client"


def _require_remaining_admin(db: Session, membership: ClientMembership) -> None:
    if membership.role != "admin":
        return
    admin_count = db.scalar(
        select(func.count(ClientMembership.id)).where(
            ClientMembership.client_id == membership.client_id,
            ClientMembership.role == "admin",
        )
    )
    if int(admin_count or 0) <= 1:
        raise HTTPException(
            status_code=409, detail="De laatste klantbeheerder moet behouden blijven"
        )


@router.patch("/clients/{client_id}/members/{user_id}", response_model=ClientMemberRead)
def update_client_member(
    client_id: UUID,
    user_id: UUID,
    payload: ClientMemberUpdate,
    principal: Principal = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    require_client_access(db, principal, client_id, admin=True)
    if principal.user_id == user_id:
        raise HTTPException(status_code=409, detail="Je kunt je eigen rol niet wijzigen")
    user = db.get(User, user_id)
    membership = db.scalar(
        select(ClientMembership).where(
            ClientMembership.client_id == client_id,
            ClientMembership.user_id == user_id,
        )
    )
    if not user or not membership:
        raise HTTPException(status_code=404, detail="Gebruiker niet gevonden")
    if user.role == "superuser":
        raise HTTPException(status_code=403, detail="De superuser kan niet worden gewijzigd")
    if (
        payload.role == "admin"
        and membership.role != "admin"
        and principal.role != "superuser"
        and not principal.is_api_key
    ):
        raise HTTPException(status_code=403, detail="Alleen de superuser kan beheerders promoveren")
    if membership.role == "admin" and payload.role != "admin":
        _require_remaining_admin(db, membership)
    old_role = membership.role
    membership.role = payload.role
    _sync_global_role(db, user)
    revoked_sessions = revoke_user_sessions(db, user.id)
    record_security_event(
        db,
        event_type="membership.role_changed",
        result="succeeded",
        summary="Klantrol gewijzigd",
        actor_user_id=principal.user_id,
        client_id=client_id,
        target_type="user",
        target_id=user.id,
        details={
            "old_role": old_role,
            "new_role": payload.role,
            "revoked_sessions": revoked_sessions,
        },
    )
    db.commit()
    db.refresh(user)
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "global_role": user.role,
        "client_role": membership.role,
        "is_active": user.is_active,
    }


@router.delete("/clients/{client_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client_member(
    client_id: UUID,
    user_id: UUID,
    principal: Principal = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> Response:
    require_client_access(db, principal, client_id, admin=True)
    if principal.user_id == user_id:
        raise HTTPException(status_code=409, detail="Je kunt je eigen toegang niet verwijderen")
    user = db.get(User, user_id)
    membership = db.scalar(
        select(ClientMembership).where(
            ClientMembership.client_id == client_id,
            ClientMembership.user_id == user_id,
        )
    )
    if not user or not membership:
        raise HTTPException(status_code=404, detail="Gebruiker niet gevonden")
    if user.role == "superuser":
        raise HTTPException(status_code=403, detail="De superuser kan niet worden verwijderd")
    _require_remaining_admin(db, membership)
    old_role = membership.role
    db.delete(membership)
    db.flush()
    _sync_global_role(db, user)
    revoked_sessions = revoke_user_sessions(db, user.id)
    record_security_event(
        db,
        event_type="membership.removed",
        result="succeeded",
        summary="Klanttoegang verwijderd",
        actor_user_id=principal.user_id,
        client_id=client_id,
        target_type="user",
        target_id=user.id,
        details={"old_role": old_role, "revoked_sessions": revoked_sessions},
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _valid_invitation(token: str, db: Session) -> UserInvitation:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    invitation = db.scalar(select(UserInvitation).where(UserInvitation.token_hash == token_hash))
    now = datetime.now(UTC)
    expires_at = invitation.expires_at if invitation else None
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (
        not invitation
        or invitation.accepted_at
        or invitation.revoked_at
        or not expires_at
        or expires_at <= now
    ):
        raise HTTPException(status_code=410, detail="Invitation is invalid or expired")
    return invitation


@public_router.get("/invitations/{token}", response_model=InvitationPreview)
def preview_invitation(token: str, db: Session = Depends(get_db)) -> UserInvitation:
    return _valid_invitation(token, db)


@public_router.post("/invitations/{token}/accept", status_code=status.HTTP_204_NO_CONTENT)
def accept_invitation(
    token: str,
    payload: InvitationAccept,
    response: Response,
    seo_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> Response:
    invitation = _valid_invitation(token, db)
    now = datetime.now(UTC)
    user = db.scalar(select(User).where(func.lower(User.email) == invitation.email.lower()))
    if user:
        if session_user_id(seo_session) != user.id and not verify_password(
            payload.password, user.password_hash
        ):
            raise HTTPException(
                status_code=409,
                detail="Log eerst in of gebruik het huidige wachtwoord van het bestaande account",
            )
        if db.scalar(
            select(ClientMembership.id).where(
                ClientMembership.user_id == user.id,
                ClientMembership.client_id == invitation.client_id,
            )
        ):
            raise HTTPException(status_code=409, detail="Gebruiker heeft al toegang tot deze klant")
        user.is_active = True
    else:
        user = User(
            email=invitation.email,
            display_name=None,
            role=invitation.role,
            password_hash=hash_password(payload.password),
        )
        db.add(user)
        db.flush()
    db.add(ClientMembership(user_id=user.id, client_id=invitation.client_id, role=invitation.role))
    db.flush()
    _sync_global_role(db, user)
    invitation.accepted_at = now
    record_security_event(
        db,
        event_type="invitation.accepted",
        result="succeeded",
        summary="Gebruikersuitnodiging geaccepteerd",
        actor_user_id=user.id,
        client_id=invitation.client_id,
        target_type="invitation",
        target_id=invitation.id,
        details={"role": invitation.role},
    )
    db.commit()
    response.set_cookie(
        "seo_session",
        create_session_token(user.id),
        max_age=60 * 60 * 12,
        httponly=True,
        secure=get_settings().app_env == "production",
        samesite="lax",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal, get_db
from app.models.user import User, UserSession

SESSION_TTL_SECONDS = 60 * 60 * 12


def create_session_token(user_id: UUID) -> str:
    token = secrets.token_urlsafe(32)
    with SessionLocal() as db:
        db.add(
            UserSession(
                user_id=user_id,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                expires_at=datetime.now(UTC) + timedelta(seconds=SESSION_TTL_SECONDS),
            )
        )
        db.commit()
    return token


def session_user_id(token: str | None) -> UUID | None:
    if not token:
        return None
    now = datetime.now(UTC)
    with SessionLocal() as db:
        session = db.scalar(
            select(UserSession).where(
                UserSession.token_hash == hashlib.sha256(token.encode()).hexdigest(),
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
            )
        )
        return session.user_id if session else None


def revoke_session_token(token: str | None) -> None:
    if not token:
        return
    with SessionLocal() as db:
        session = db.scalar(
            select(UserSession).where(
                UserSession.token_hash == hashlib.sha256(token.encode()).hexdigest(),
                UserSession.revoked_at.is_(None),
            )
        )
        if session:
            session.revoked_at = datetime.now(UTC)
            db.commit()


def is_valid_session_token(token: str | None) -> bool:
    return session_user_id(token) is not None


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$", maxsplit=5)
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=32,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), expected)


@dataclass(frozen=True)
class Principal:
    user_id: UUID | None
    role: str
    is_api_key: bool = False


def require_api_key(
    x_api_key: str | None = Header(default=None),
    seo_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> Principal:
    valid_key = x_api_key is not None and hmac.compare_digest(x_api_key, get_settings().api_key)
    if valid_key:
        return Principal(user_id=None, role="superuser", is_api_key=True)
    user_id = session_user_id(seo_session)
    user = db.get(User, user_id) if user_id else None
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return Principal(user_id=user.id, role=user.role)

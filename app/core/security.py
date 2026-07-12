import base64
import binascii
import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from uuid import UUID

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User

SESSION_TTL_SECONDS = 60 * 60 * 12


def create_session_token(user_id: UUID) -> str:
    expires_at = str(int(time.time()) + SESSION_TTL_SECONDS)
    payload = f"{user_id}.{expires_at}"
    signature = hmac.new(
        get_settings().api_key.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}.{signature}".encode()).decode()


def session_user_id(token: str | None) -> UUID | None:
    if not token:
        return False
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        user_id, expires_at, signature = decoded.split(".", maxsplit=2)
        parsed_user_id = UUID(user_id)
        if int(expires_at) < int(time.time()):
            return None
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    expected = hmac.new(
        get_settings().api_key.encode(), f"{user_id}.{expires_at}".encode(), hashlib.sha256
    ).hexdigest()
    return parsed_user_id if hmac.compare_digest(signature, expected) else None


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

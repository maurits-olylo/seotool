import base64
import binascii
import hashlib
import hmac
import time

from fastapi import Cookie, Header, HTTPException, status

from app.core.config import get_settings

SESSION_TTL_SECONDS = 60 * 60 * 12


def create_session_token() -> str:
    expires_at = str(int(time.time()) + SESSION_TTL_SECONDS)
    signature = hmac.new(
        get_settings().api_key.encode(), expires_at.encode(), hashlib.sha256
    ).hexdigest()
    return base64.urlsafe_b64encode(f"{expires_at}.{signature}".encode()).decode()


def is_valid_session_token(token: str | None) -> bool:
    if not token:
        return False
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        expires_at, signature = decoded.split(".", maxsplit=1)
        if int(expires_at) < int(time.time()):
            return False
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return False
    expected = hmac.new(
        get_settings().api_key.encode(), expires_at.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


def require_api_key(
    x_api_key: str | None = Header(default=None),
    seo_session: str | None = Cookie(default=None),
) -> None:
    valid_key = x_api_key is not None and hmac.compare_digest(x_api_key, get_settings().api_key)
    if not valid_key and not is_valid_session_token(seo_session):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import OAuthState

GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
]
BING_SCOPES = ["webmaster.read"]


def oauth_error_message(provider: str, response: Any) -> str:
    """Return a safe, actionable OAuth error without storing tokens or response bodies."""
    try:
        payload = response.json()
    except (TypeError, ValueError):
        payload = {}
    error = str(payload.get("error") or "").strip()
    description = str(payload.get("error_description") or "").strip()
    detail = ": ".join(part for part in (error, description) if part)
    if error == "invalid_grant":
        return f"{provider} authorization is expired or revoked; reconnect required (invalid_grant)"
    return f"{provider} access token could not be refreshed{f' ({detail})' if detail else ''}"


def google_is_configured() -> bool:
    settings = get_settings()
    return all(
        [
            settings.google_client_id,
            settings.google_client_secret,
            settings.google_redirect_uri,
            settings.token_encryption_key,
        ]
    )


def google_authorization_url(state: str) -> str:
    settings = get_settings()
    parameters = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(parameters)}"


def bing_is_configured() -> bool:
    settings = get_settings()
    return all(
        [
            settings.bing_client_id,
            settings.bing_client_secret,
            settings.bing_redirect_uri,
            settings.token_encryption_key,
        ]
    )


def bing_authorization_url(state: str) -> str:
    settings = get_settings()
    parameters = {
        "client_id": settings.bing_client_id,
        "redirect_uri": settings.bing_redirect_uri,
        "response_type": "code",
        "scope": " ".join(BING_SCOPES),
        "state": state,
    }
    return f"https://www.bing.com/webmasters/oauth/authorize?{urlencode(parameters)}"


def create_oauth_state(
    db: Session, client_id: UUID, user_id: UUID, session_id: UUID, provider: str
) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        OAuthState(
            client_id=client_id,
            user_id=user_id,
            session_id=session_id,
            provider=provider,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
    )
    db.commit()
    return token


def consume_oauth_state(db: Session, state: str, provider: str, session_id: UUID) -> UUID:
    record = db.scalar(
        select(OAuthState).where(
            OAuthState.token_hash == hashlib.sha256(state.encode()).hexdigest(),
            OAuthState.provider == provider,
            OAuthState.session_id == session_id,
            OAuthState.consumed_at.is_(None),
            OAuthState.expires_at > datetime.now(UTC),
        )
    )
    if not record:
        raise ValueError("OAuth state is invalid or expired")
    record.consumed_at = datetime.now(UTC)
    db.commit()
    return record.client_id


def encrypt_token(token: str | None) -> str | None:
    return _fernet().encrypt(token.encode()).decode() if token else None


def decrypt_token(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Stored OAuth token cannot be decrypted") from exc


def _fernet() -> Fernet:
    try:
        raw_key = bytes.fromhex(get_settings().token_encryption_key)
    except ValueError as exc:
        raise ValueError("TOKEN_ENCRYPTION_KEY must contain 64 hexadecimal characters") from exc
    if len(raw_key) != 32:
        raise ValueError("TOKEN_ENCRYPTION_KEY must contain 64 hexadecimal characters")
    return Fernet(base64.urlsafe_b64encode(raw_key))

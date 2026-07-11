import base64
import binascii
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
]


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


def google_authorization_url(client_id: UUID) -> str:
    settings = get_settings()
    parameters = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": create_oauth_state(client_id),
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(parameters)}"


def create_oauth_state(client_id: UUID, *, lifetime_seconds: int = 600) -> str:
    payload = json.dumps(
        {"client_id": str(client_id), "expires_at": int(time.time()) + lifetime_seconds},
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(_signing_key(), payload, hashlib.sha256).digest()
    return f"{_b64encode(payload)}.{_b64encode(signature)}"


def parse_oauth_state(state: str) -> UUID:
    try:
        payload_encoded, signature_encoded = state.split(".", maxsplit=1)
        payload = _b64decode(payload_encoded)
        signature = _b64decode(signature_encoded)
        expected = hmac.new(_signing_key(), payload, hashlib.sha256).digest()
        data = json.loads(payload)
        if not hmac.compare_digest(signature, expected) or data["expires_at"] < time.time():
            raise ValueError("OAuth state is invalid or expired")
        return UUID(data["client_id"])
    except (binascii.Error, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("OAuth state is invalid or expired") from exc


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


def _signing_key() -> bytes:
    return (get_settings().token_encryption_key or get_settings().api_key).encode()


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

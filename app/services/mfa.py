import base64
import hashlib
import hmac
import secrets
import struct
import time

TOTP_PERIOD_SECONDS = 30
TOTP_DIGITS = 6


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_code(secret: str, *, at_time: int | None = None) -> str:
    counter = (at_time if at_time is not None else int(time.time())) // TOTP_PERIOD_SECONDS
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (
        10**TOTP_DIGITS
    )
    return f"{number:0{TOTP_DIGITS}d}"


def valid_totp_counter(
    secret: str,
    code: str,
    *,
    at_time: int | None = None,
    last_counter: int | None = None,
) -> int | None:
    if len(code) != TOTP_DIGITS or not code.isdigit():
        return None
    now = at_time if at_time is not None else int(time.time())
    current_counter = now // TOTP_PERIOD_SECONDS
    for counter in range(current_counter - 1, current_counter + 2):
        if last_counter is not None and counter <= last_counter:
            continue
        if hmac.compare_digest(totp_code(secret, at_time=counter * TOTP_PERIOD_SECONDS), code):
            return counter
    return None


def generate_recovery_codes(count: int = 10) -> list[str]:
    return [f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(count)]


def recovery_code_hash(code: str) -> str:
    return hashlib.sha256(code.strip().lower().encode()).hexdigest()


def consume_recovery_code(code: str, stored_hashes: list[str]) -> list[str] | None:
    candidate = recovery_code_hash(code)
    for index, stored in enumerate(stored_hashes):
        if hmac.compare_digest(candidate, stored):
            return stored_hashes[:index] + stored_hashes[index + 1 :]
    return None

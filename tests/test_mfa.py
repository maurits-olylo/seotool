from app.services.mfa import (
    consume_recovery_code,
    generate_recovery_codes,
    generate_totp_secret,
    recovery_code_hash,
    totp_code,
    valid_totp_counter,
)


def test_totp_accepts_current_window_and_blocks_replay() -> None:
    secret = generate_totp_secret()
    at_time = 1_800_000_000
    code = totp_code(secret, at_time=at_time)
    counter = valid_totp_counter(secret, code, at_time=at_time)

    assert counter == at_time // 30
    assert valid_totp_counter(secret, code, at_time=at_time, last_counter=counter) is None
    assert valid_totp_counter(secret, "not-a-code", at_time=at_time) is None


def test_recovery_code_is_single_use_and_only_hash_is_stored() -> None:
    codes = generate_recovery_codes(2)
    hashes = [recovery_code_hash(code) for code in codes]

    assert all(code not in hashes for code in codes)
    remaining = consume_recovery_code(codes[0], hashes)
    assert remaining == [hashes[1]]
    assert consume_recovery_code(codes[0], remaining) is None

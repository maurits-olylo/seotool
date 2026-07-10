import socket

import pytest

from app.services.security import validate_public_http_url
from app.services.url_normalization import InvalidUrlError


def test_blocks_localhost() -> None:
    with pytest.raises(InvalidUrlError):
        validate_public_http_url("http://localhost/admin")


def test_blocks_private_dns_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.2", 443))],
    )
    with pytest.raises(InvalidUrlError):
        validate_public_http_url("https://internal.example")

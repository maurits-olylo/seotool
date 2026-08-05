import socket

import pytest

from app.services.security import resolve_public_http_target, validate_public_http_url
from app.services.url_normalization import InvalidUrlError


def test_blocks_localhost() -> None:
    with pytest.raises(InvalidUrlError):
        validate_public_http_url("http://localhost/admin")


def test_blocks_private_dns_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.2", 443))],
    )
    with pytest.raises(InvalidUrlError):
        validate_public_http_url("https://internal.example")


def test_blocks_mixed_public_and_private_dns_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ],
    )

    with pytest.raises(InvalidUrlError):
        resolve_public_http_target("https://example.com/path")


def test_resolves_to_pinned_url_and_preserves_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )

    target = resolve_public_http_target("https://Example.com/path?q=1#fragment")

    assert target.connect_url == "https://93.184.216.34/path?q=1"
    assert target.host_header == "example.com"
    assert target.sni_hostname == "example.com"


@pytest.mark.parametrize(
    "url",
    ["https://user:secret@example.com", "https://example.com:8443/path"],
)
def test_blocks_credentials_and_nonstandard_ports(url: str) -> None:
    with pytest.raises(InvalidUrlError):
        resolve_public_http_target(url)

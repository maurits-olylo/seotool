import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit, urlunsplit

from app.services.url_normalization import InvalidUrlError


@dataclass(frozen=True)
class ResolvedHttpTarget:
    connect_url: str
    host_header: str
    sni_hostname: str


def resolve_public_http_target(url: str) -> ResolvedHttpTarget:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise InvalidUrlError("Only absolute HTTP and HTTPS URLs are allowed")
    if parts.username is not None or parts.password is not None:
        raise InvalidUrlError("Credentials in URLs are not allowed")

    hostname = parts.hostname.lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise InvalidUrlError("Localhost is not allowed")

    default_port = 443 if parts.scheme == "https" else 80
    try:
        port = parts.port or default_port
    except ValueError as exc:
        raise InvalidUrlError("URL contains an invalid port") from exc
    if port not in {80, 443}:
        raise InvalidUrlError("Only standard HTTP and HTTPS ports are allowed")

    try:
        addresses = {
            ipaddress.ip_address(item[4][0])
            for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as exc:
        raise InvalidUrlError("Hostname could not be resolved") from exc
    except ValueError as exc:
        raise InvalidUrlError("Hostname resolved to an invalid address") from exc
    if not addresses:
        raise InvalidUrlError("Hostname has no addresses")
    for address in addresses:
        if not address.is_global:
            raise InvalidUrlError("Private, local and reserved addresses are not allowed")

    address = min(addresses, key=lambda value: (value.version, int(value)))
    address_host = f"[{address.compressed}]" if address.version == 6 else address.compressed
    include_port = port != default_port
    connect_netloc = f"{address_host}:{port}" if include_port else address_host
    host_header = f"{hostname}:{port}" if include_port else hostname
    connect_url = urlunsplit(SplitResult(parts.scheme, connect_netloc, parts.path, parts.query, ""))
    return ResolvedHttpTarget(
        connect_url=connect_url,
        host_header=host_header,
        sni_hostname=hostname,
    )


def validate_public_http_url(url: str) -> None:
    resolve_public_http_target(url)

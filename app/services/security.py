import ipaddress
import socket
from urllib.parse import urlsplit

from app.services.url_normalization import InvalidUrlError


def validate_public_http_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise InvalidUrlError("Only absolute HTTP and HTTPS URLs are allowed")
    hostname = parts.hostname.lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise InvalidUrlError("Localhost is not allowed")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, parts.port or 443)}
    except socket.gaierror as exc:
        raise InvalidUrlError("Hostname could not be resolved") from exc
    if not addresses:
        raise InvalidUrlError("Hostname has no addresses")
    for value in addresses:
        address = ipaddress.ip_address(value)
        if not address.is_global:
            raise InvalidUrlError("Private, local and reserved addresses are not allowed")

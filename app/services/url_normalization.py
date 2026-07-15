from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

TRACKING_PARAMETERS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_content",
        "utm_term",
        "gclid",
        "fbclid",
        "msclkid",
    }
)


class InvalidUrlError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizationOptions:
    ignored_query_parameters: frozenset[str] = frozenset()
    remove_trailing_slash: bool = True


def normalize_url(
    url: str,
    *,
    base_url: str | None = None,
    options: NormalizationOptions | None = None,
) -> str:
    options = options or NormalizationOptions()
    try:
        absolute_url = urljoin(base_url, url) if base_url else url
        parts = urlsplit(absolute_url.strip())
    except ValueError as exc:
        raise InvalidUrlError("Invalid URL syntax") from exc
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        raise InvalidUrlError("Only HTTP and HTTPS URLs are supported")
    if not parts.hostname:
        raise InvalidUrlError("URL must contain a hostname")

    hostname = parts.hostname.lower().rstrip(".")
    try:
        port = parts.port
    except ValueError as exc:
        raise InvalidUrlError("Invalid port") from exc
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = hostname if port is None or default_port else f"{hostname}:{port}"

    path = _normalize_path(parts.path)
    if options.remove_trailing_slash and path != "/":
        path = path.rstrip("/")

    ignored = TRACKING_PARAMETERS | {item.lower() for item in options.ignored_query_parameters}
    query_items = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in ignored
    ]
    query = urlencode(sorted(query_items), doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def _normalize_path(path: str) -> str:
    segments: list[str] = []
    for segment in path.split("/"):
        if not segment or segment == ".":
            continue
        if segment == "..":
            if segments:
                segments.pop()
            continue
        segments.append(segment)
    return "/" + "/".join(segments)

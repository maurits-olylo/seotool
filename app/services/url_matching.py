from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from app.services.url_normalization import normalize_url


def find_equivalent_website_url_id(
    url_map: dict[str, UUID], raw_url: str, *, base_url: str
) -> UUID | None:
    """Match exact URLs first, then the equivalent root/www host variant."""
    normalized = normalize_url(raw_url)
    if exact := url_map.get(normalized):
        return exact
    parts = urlsplit(normalized)
    base_host = (urlsplit(base_url).hostname or "").lower().rstrip(".")
    target_host = (parts.hostname or "").lower().rstrip(".")
    bare_host = target_host.removeprefix("www.")
    if not base_host or bare_host != base_host.removeprefix("www."):
        return None
    for host in (bare_host, f"www.{bare_host}"):
        candidate = urlunsplit((parts.scheme, host, parts.path, parts.query, ""))
        if match := url_map.get(candidate):
            return match
    return None

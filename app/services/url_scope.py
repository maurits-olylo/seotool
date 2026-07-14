from urllib.parse import urlsplit


def _normalized_host(value: str) -> str:
    candidate = value.strip().lower().rstrip(".")
    if "://" in candidate:
        return (urlsplit(candidate).hostname or "").lower().rstrip(".")
    return candidate.split("/", 1)[0].split(":", 1)[0].rstrip(".")


def is_url_in_website_scope(
    url: str,
    *,
    base_url: str,
    allowed_subdomains: list[str] | None = None,
) -> bool:
    """Allow only the configured website host and explicitly allowed hosts."""
    target_host = (urlsplit(url).hostname or "").lower().rstrip(".")
    base_host = (urlsplit(base_url).hostname or "").lower().rstrip(".")
    if not target_host or not base_host:
        return False
    if target_host == base_host:
        return True
    if target_host.removeprefix("www.") == base_host.removeprefix("www.") and (
        target_host.startswith("www.") or base_host.startswith("www.")
    ):
        return True
    for value in allowed_subdomains or []:
        allowed = _normalized_host(value)
        if not allowed:
            continue
        if allowed.startswith("*.") and target_host.endswith(allowed[1:]):
            return True
        if target_host == allowed:
            return True
    return False

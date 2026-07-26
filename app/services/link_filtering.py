from urllib.parse import unquote, urlsplit

PLACEHOLDER_MARKERS = ("${", "{{", "{%", "[[", "cms://")


def is_non_navigational_link_target(url: str) -> bool:
    """Recognize technical link values that must not become crawl/link issues."""
    lowered = unquote(url).lower()
    if any(marker in lowered for marker in PLACEHOLDER_MARKERS):
        return True
    return urlsplit(url).path.rstrip("/").lower() == "/cdn-cgi/l/email-protection"

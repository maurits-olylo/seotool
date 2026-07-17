from urllib.parse import quote, urlsplit, urlunsplit

from app.models.crawl import ElementLocation


def build_live_jump_url(source_url: str, location: ElementLocation) -> str | None:
    base_url = _without_fragment(source_url)
    if location.element_id:
        return f"{base_url}#{quote(location.element_id, safe='')}"
    text = (location.visible_text or "").strip()
    if not text:
        return None
    if location.text_is_unique:
        return f"{base_url}#:~:text={quote(text, safe='')}"
    if not location.context_is_unique:
        return None
    prefix = (location.text_prefix or "").strip()
    suffix = (location.text_suffix or "").strip()
    if not prefix and not suffix:
        return None
    directive = quote(text, safe="")
    if prefix:
        directive = f"{quote(prefix, safe='')}-,{directive}"
    if suffix:
        directive = f"{directive},-{quote(suffix, safe='')}"
    return f"{base_url}#:~:text={directive}"


def _without_fragment(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))

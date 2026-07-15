import json
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import structlog
from bs4 import BeautifulSoup

from app.services.hashing import stable_hash
from app.services.url_normalization import InvalidUrlError, normalize_url

INVALID_JSON_LD_MARKER = "_seo_monitor_invalid_json_ld"
logger = structlog.get_logger()


@dataclass(frozen=True)
class ExtractedLink:
    target_url: str
    anchor_text: str
    is_internal: bool
    is_nofollow: bool


@dataclass(frozen=True)
class ExtractedPage:
    title: str | None
    meta_description: str | None
    canonical: str | None
    meta_robots: str | None
    html_lang: str | None
    headings: dict[str, list[str]]
    word_count: int
    main_content: str
    schema_types: list[str]
    schema_data: list[object]
    links: list[ExtractedLink]
    html_hash: str
    main_content_hash: str
    metadata_hash: str
    links_hash: str
    schema_hash: str


def extract_page(html: str, page_url: str) -> ExtractedPage:
    soup = BeautifulSoup(html, "lxml")
    title = _text(soup.title)
    description = _meta_content(soup, "description")
    robots = _meta_content(soup, "robots")
    canonical_tag = soup.find("link", rel=lambda value: value and "canonical" in value)
    canonical = None
    if canonical_tag and canonical_tag.get("href"):
        canonical = _resolve_page_url(
            page_url,
            str(canonical_tag.get("href")),
            element="canonical",
        )
    headings = {
        level: [_clean_text(tag.get_text(" ", strip=True)) for tag in soup.find_all(level)]
        for level in ("h1", "h2", "h3", "h4", "h5", "h6")
    }

    main = soup.find("main") or soup.body or soup
    main_copy = BeautifulSoup(str(main), "lxml")
    for tag in main_copy(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()
    main_content = _clean_text(main_copy.get_text(" ", strip=True))

    schema_data, schema_types = _extract_json_ld(soup)
    links = _extract_links(soup, page_url)
    metadata = {
        "title": title,
        "description": description,
        "canonical": canonical,
        "robots": robots,
        "headings": headings,
    }
    link_values: set[tuple[str, str, bool]] = set()
    for link in links:
        if not link.is_internal:
            continue
        try:
            target_url = normalize_url(link.target_url)
        except InvalidUrlError:
            continue
        link_values.add((target_url, link.anchor_text, link.is_nofollow))
    link_data = [
        {"url": url, "anchor": anchor, "nofollow": nofollow}
        for url, anchor, nofollow in sorted(link_values)
    ]
    stable_schema_data = sorted(
        schema_data,
        key=lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False),
    )
    return ExtractedPage(
        title=title,
        meta_description=description,
        canonical=canonical,
        meta_robots=robots,
        html_lang=soup.html.get("lang") if soup.html else None,
        headings=headings,
        word_count=len(re.findall(r"\b\w+\b", main_content, flags=re.UNICODE)),
        main_content=main_content,
        schema_types=schema_types,
        schema_data=schema_data,
        links=links,
        html_hash=stable_hash(html),
        main_content_hash=stable_hash(main_content),
        metadata_hash=stable_hash(metadata),
        links_hash=stable_hash(link_data),
        schema_hash=stable_hash(stable_schema_data),
    )


def _text(tag: object) -> str | None:
    if tag is None or not hasattr(tag, "get_text"):
        return None
    value = _clean_text(tag.get_text(" ", strip=True))
    return value or None


def _meta_content(soup: BeautifulSoup, name: str) -> str | None:
    tag = soup.find("meta", attrs={"name": re.compile(f"^{re.escape(name)}$", re.I)})
    return _clean_text(str(tag.get("content"))) if tag and tag.get("content") else None


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _extract_json_ld(soup: BeautifulSoup) -> tuple[list[object], list[str]]:
    data: list[object] = []
    types: set[str] = set()
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            value = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            data.append({INVALID_JSON_LD_MARKER: True})
            continue
        data.append(value)
        _collect_schema_types(value, types)
    return data, sorted(types)


def _collect_schema_types(value: object, types: set[str]) -> None:
    if isinstance(value, dict):
        schema_type = value.get("@type")
        if isinstance(schema_type, str):
            types.add(schema_type)
        elif isinstance(schema_type, list):
            types.update(str(item) for item in schema_type)
        for child in value.values():
            _collect_schema_types(child, types)
    elif isinstance(value, list):
        for child in value:
            _collect_schema_types(child, types)


def _extract_links(soup: BeautifulSoup, page_url: str) -> list[ExtractedLink]:
    page_host = urlsplit(page_url).hostname
    links: list[ExtractedLink] = []
    for tag in soup.find_all("a", href=True):
        target = _resolve_page_url(page_url, str(tag["href"]), element="link")
        if target is None:
            continue
        try:
            target_parts = urlsplit(target)
        except ValueError:
            _log_invalid_page_url(page_url, target, element="link")
            continue
        if target_parts.scheme not in {"http", "https"}:
            continue
        rel = {str(item).lower() for item in (tag.get("rel") or [])}
        links.append(
            ExtractedLink(
                target_url=target,
                anchor_text=_clean_text(tag.get_text(" ", strip=True)),
                is_internal=target_parts.hostname == page_host,
                is_nofollow="nofollow" in rel,
            )
        )
    return links


def _resolve_page_url(page_url: str, raw_url: str, *, element: str) -> str | None:
    try:
        return urljoin(page_url, raw_url)
    except ValueError:
        _log_invalid_page_url(page_url, raw_url, element=element)
        return None


def _log_invalid_page_url(page_url: str, raw_url: str, *, element: str) -> None:
    logger.warning(
        "crawl_html_url_skipped_invalid_syntax",
        source_url=_safe_log_value(page_url),
        target_url=_safe_log_value(raw_url),
        element=element,
    )


def _safe_log_value(value: str) -> str:
    without_query = value.split("?", 1)[0].split("#", 1)[0]
    if "@" in without_query:
        without_query = without_query.rsplit("@", 1)[-1]
    return without_query[:1000]

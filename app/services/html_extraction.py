import json
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import structlog
from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

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
class ExtractedElement:
    element_type: str
    target_url: str | None
    visible_text: str | None
    element_id: str | None
    css_selector: str | None
    xpath: str | None
    html_fragment: str
    occurrence_index: int
    text_prefix: str | None
    text_suffix: str | None
    text_is_unique: bool
    context_is_unique: bool
    rendered_dynamically: bool
    issue_types: list[str]


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
    elements: list[ExtractedElement]
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
    elements = _extract_elements(soup, page_url)
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
        elements=elements,
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
    for tag in soup.find_all(["a", "button"]):
        target = _element_target(tag, page_url)
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


def _extract_elements(soup: BeautifulSoup, page_url: str) -> list[ExtractedElement]:
    tags = list(soup.find_all(["a", "button", "h1", "h2", "h3", "img"]))
    text_counts: dict[tuple[str, str], int] = {}
    raw_items: list[dict[str, object]] = []
    occurrences: dict[tuple[str, str, str], int] = {}
    heading_counts = {
        (tag.name, _clean_text(tag.get_text(" ", strip=True)).casefold()): 0
        for tag in tags
        if tag.name in {"h1", "h2", "h3"}
    }
    for tag in tags:
        visible_text = _element_text(tag)
        if visible_text:
            text_key = (_text_group(tag), visible_text.casefold())
            text_counts[text_key] = text_counts.get(text_key, 0) + 1
        if tag.name in {"h1", "h2", "h3"} and visible_text:
            heading_counts[(tag.name, visible_text.casefold())] += 1

    context_counts: dict[tuple[str, str, str, str], int] = {}
    for tag in tags:
        visible_text = _element_text(tag)
        target_url = _element_target(tag, page_url)
        prefix = _nearby_text(tag, previous=True)
        suffix = _nearby_text(tag, previous=False)
        occurrence_key = (tag.name, visible_text or "", target_url or "")
        occurrences[occurrence_key] = occurrences.get(occurrence_key, 0) + 1
        context_key = (
            _text_group(tag),
            (visible_text or "").casefold(),
            (prefix or "").casefold(),
            (suffix or "").casefold(),
        )
        context_counts[context_key] = context_counts.get(context_key, 0) + 1
        raw_items.append(
            {
                "tag": tag,
                "visible_text": visible_text,
                "target_url": target_url,
                "prefix": prefix,
                "suffix": suffix,
                "occurrence_index": occurrences[occurrence_key],
                "context_key": context_key,
            }
        )

    result: list[ExtractedElement] = []
    h1_count = sum(1 for tag in tags if tag.name == "h1")
    for item in raw_items:
        tag = item["tag"]
        assert isinstance(tag, Tag)
        visible_text = item["visible_text"]
        assert isinstance(visible_text, str) or visible_text is None
        issue_types = _initial_element_issue_types(
            tag,
            visible_text,
            h1_count=h1_count,
            heading_counts=heading_counts,
        )
        text_key = (_text_group(tag), visible_text.casefold()) if visible_text else None
        result.append(
            ExtractedElement(
                element_type=tag.name,
                target_url=item["target_url"] if isinstance(item["target_url"], str) else None,
                visible_text=visible_text,
                element_id=_clean_text(str(tag.get("id"))) if tag.get("id") else None,
                css_selector=_css_selector(tag),
                xpath=_xpath(tag),
                html_fragment=str(tag)[:2000],
                occurrence_index=int(item["occurrence_index"]),
                text_prefix=item["prefix"] if isinstance(item["prefix"], str) else None,
                text_suffix=item["suffix"] if isinstance(item["suffix"], str) else None,
                text_is_unique=bool(text_key and text_counts.get(text_key) == 1),
                context_is_unique=context_counts[item["context_key"]] == 1,
                rendered_dynamically=False,
                issue_types=issue_types,
            )
        )
    return result


def _element_text(tag: Tag) -> str | None:
    text = _clean_text(tag.get_text(" ", strip=True))
    if not text and tag.name == "img":
        figure = tag.find_parent("figure")
        caption = figure.find("figcaption") if figure else None
        text = _clean_text(caption.get_text(" ", strip=True)) if caption else ""
    return text or None


def _element_target(tag: Tag, page_url: str) -> str | None:
    raw_target: object = None
    if tag.name == "a":
        raw_target = tag.get("href")
    elif tag.name == "img":
        raw_target = tag.get("src")
    elif tag.name == "button":
        form = tag.find_parent("form")
        raw_target = tag.get("formaction") or (form.get("action") if form else None)
    if raw_target is None:
        return None
    raw = _clean_text(str(raw_target))
    if not raw:
        return None
    return _resolve_page_url(page_url, raw, element=tag.name)


def _initial_element_issue_types(
    tag: Tag,
    visible_text: str | None,
    *,
    h1_count: int,
    heading_counts: dict[tuple[str, str], int],
) -> list[str]:
    issues: list[str] = []
    if tag.name == "h1" and h1_count > 1:
        issues.append("multiple_h1")
    if (
        tag.name in {"h1", "h2", "h3"}
        and visible_text
        and heading_counts.get((tag.name, visible_text.casefold()), 0) > 1
    ):
        issues.append("duplicate_heading_text")
    if tag.name in {"a", "button"}:
        form = tag.find_parent("form") if tag.name == "button" else None
        raw = _clean_text(
            str(
                tag.get("href")
                or tag.get("formaction")
                or (form.get("action") if form else "")
            )
        )
        placeholder = bool(re.search(r"(?:\{\{|\{%|\[\[|cms://|\$\{)", raw, re.I))
        invalid = not raw or raw == "#" or raw.lower().startswith("javascript:")
        is_cta = bool(
            re.search(
                r"\b(solliciteer|reageer|aanmelden|apply|inschrijven)\b",
                visible_text or "",
                re.I,
            )
        )
        if placeholder:
            issues.append("cms_link_placeholder")
        elif invalid:
            issues.append("broken_application_cta" if is_cta else "invalid_or_empty_link")
    return issues


def _text_group(tag: Tag) -> str:
    return "heading" if tag.name in {"h1", "h2", "h3"} else "interactive"


def _nearby_text(tag: Tag, *, previous: bool) -> str | None:
    finder = tag.find_previous if previous else tag.find_next
    node = finder(string=True)
    while isinstance(node, NavigableString):
        parent = node.parent
        inside_tag = bool(parent is tag or (isinstance(parent, Tag) and tag in parent.parents))
        if parent is not None and not inside_tag:
            value = _clean_text(str(node))
            if value:
                words = value.split()
                selected = words[-8:] if previous else words[:8]
                return " ".join(selected)[:160]
        node = finder(string=True) if node is None else (
            node.find_previous(string=True) if previous else node.find_next(string=True)
        )
    return None


def _css_selector(tag: Tag) -> str | None:
    if tag.get("id"):
        value = str(tag.get("id")).replace('"', '\\"')
        return f'{tag.name}[id="{value}"]'
    parts: list[str] = []
    current: Tag | None = tag
    while current is not None and current.name not in {"[document]", "html"}:
        siblings = (
            list(current.parent.find_all(current.name, recursive=False))
            if current.parent
            else []
        )
        position = siblings.index(current) + 1 if current in siblings else 1
        parts.append(f"{current.name}:nth-of-type({position})")
        current = current.parent if isinstance(current.parent, Tag) else None
    return " > ".join(reversed(parts)) or None


def _xpath(tag: Tag) -> str | None:
    parts: list[str] = []
    current: Tag | None = tag
    while current is not None and current.name != "[document]":
        siblings = (
            list(current.parent.find_all(current.name, recursive=False))
            if current.parent
            else []
        )
        position = siblings.index(current) + 1 if current in siblings else 1
        parts.append(f"{current.name}[{position}]")
        current = current.parent if isinstance(current.parent, Tag) else None
    return "/" + "/".join(reversed(parts)) if parts else None


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

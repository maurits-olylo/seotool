import json
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from app.services.hashing import stable_hash


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
    canonical = (
        urljoin(page_url, canonical_tag.get("href"))
        if canonical_tag and canonical_tag.get("href")
        else None
    )
    headings = {
        level: [_clean_text(tag.get_text(" ", strip=True)) for tag in soup.find_all(level)]
        for level in ("h1", "h2", "h3", "h4", "h5", "h6")
    }

    main = soup.find("main") or soup.find("article") or soup.body or soup
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
    link_data = [
        {"url": link.target_url, "anchor": link.anchor_text, "nofollow": link.is_nofollow}
        for link in links
    ]
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
        schema_hash=stable_hash(schema_data),
    )


def _text(tag: object) -> str | None:
    if tag is None or not hasattr(tag, "get_text"):
        return None
    value = _clean_text(tag.get_text(" ", strip=True))
    return value or None


def _meta_content(soup: BeautifulSoup, name: str) -> str | None:
    tag = soup.find("meta", attrs={"name": re.compile(f"^{re.escape(name)}$", re.I)})
    return str(tag.get("content")).strip() if tag and tag.get("content") else None


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _extract_json_ld(soup: BeautifulSoup) -> tuple[list[object], list[str]]:
    data: list[object] = []
    types: set[str] = set()
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            value = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
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
        target = urljoin(page_url, str(tag["href"]))
        if urlsplit(target).scheme not in {"http", "https"}:
            continue
        rel = {str(item).lower() for item in (tag.get("rel") or [])}
        links.append(
            ExtractedLink(
                target_url=target,
                anchor_text=_clean_text(tag.get_text(" ", strip=True)),
                is_internal=urlsplit(target).hostname == page_host,
                is_nofollow="nofollow" in rel,
            )
        )
    return links

from dataclasses import dataclass
from datetime import datetime

from lxml import etree


class InvalidSitemapError(ValueError):
    pass


@dataclass(frozen=True)
class SitemapUrl:
    location: str
    last_modified: datetime | None = None


@dataclass(frozen=True)
class SitemapDocument:
    urls: tuple[SitemapUrl, ...]
    child_sitemaps: tuple[str, ...]


def parse_sitemap(content: bytes, *, max_entries: int = 50_000) -> SitemapDocument:
    if len(content) > 50_000_000:
        raise InvalidSitemapError("Sitemap exceeds maximum size")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
    try:
        root = etree.fromstring(content, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise InvalidSitemapError("Invalid sitemap XML") from exc

    root_name = etree.QName(root).localname
    if root_name not in {"urlset", "sitemapindex"}:
        raise InvalidSitemapError("Unsupported sitemap root element")

    entries = root.xpath("./*[local-name()='url' or local-name()='sitemap']")
    if len(entries) > max_entries:
        raise InvalidSitemapError("Sitemap contains too many entries")

    urls: list[SitemapUrl] = []
    children: list[str] = []
    for entry in entries:
        locations = entry.xpath("./*[local-name()='loc']/text()")
        if not locations or not locations[0].strip():
            continue
        location = locations[0].strip()
        if etree.QName(entry).localname == "sitemap":
            children.append(location)
            continue
        modified_values = entry.xpath("./*[local-name()='lastmod']/text()")
        urls.append(
            SitemapUrl(location, _parse_datetime(modified_values[0]) if modified_values else None)
        )
    return SitemapDocument(tuple(urls), tuple(children))


def _parse_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None

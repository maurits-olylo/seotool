from pathlib import Path

import pytest

from app.services.sitemap import InvalidSitemapError, parse_sitemap

FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_urlset() -> None:
    sitemap = parse_sitemap((FIXTURES / "sitemap.xml").read_bytes())
    assert [item.location for item in sitemap.urls] == [
        "https://example.com/",
        "https://example.com/contact",
    ]
    assert sitemap.urls[0].last_modified is not None


def test_parses_sitemap_index() -> None:
    sitemap = parse_sitemap((FIXTURES / "sitemap-index.xml").read_bytes())
    assert sitemap.child_sitemaps == (
        "https://example.com/pages.xml",
        "https://example.com/posts.xml",
    )


def test_rejects_invalid_xml() -> None:
    with pytest.raises(InvalidSitemapError):
        parse_sitemap(b"<html></html>")

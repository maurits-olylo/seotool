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


def test_reports_document_quality_without_rejecting_usable_entries() -> None:
    sitemap = parse_sitemap(
        b"""<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url><loc>https://example.com/page</loc><lastmod>not-a-date</lastmod></url>
        <url><loc>https://example.com/page</loc></url>
        <url><lastmod>2026-08-04</lastmod></url>
        </urlset>"""
    )

    assert sitemap.missing_location_count == 1
    assert sitemap.duplicate_locations == ("https://example.com/page",)
    assert sitemap.invalid_last_modified_locations == ("https://example.com/page",)

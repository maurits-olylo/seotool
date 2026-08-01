import httpx
import pytest
from fastapi import HTTPException

from app.api.routes.public_estimates import _enforce_rate_limit, _requests
from app.services.public_estimate import estimate_public_website, package_for_pages


def _transport(responses: dict[str, tuple[int, str, str]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        status, content_type, body = responses.get(
            str(request.url), (404, "text/plain", "not found")
        )
        return httpx.Response(
            status,
            headers={"content-type": content_type},
            content=body.encode(),
            request=request,
        )

    return httpx.MockTransport(handler)


def test_estimate_uses_unique_internal_sitemap_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.public_estimate.validate_public_http_url", lambda _: None)
    transport = _transport(
        {
            "https://example.com/robots.txt": (
                200,
                "text/plain",
                "Sitemap: https://example.com/sitemap.xml",
            ),
            "https://example.com/sitemap.xml": (
                200,
                "application/xml",
                """<?xml version='1.0'?><urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>
                <url><loc>https://example.com/</loc></url>
                <url><loc>https://example.com/about?utm_source=test</loc></url>
                <url><loc>https://example.com/about</loc></url>
                <url><loc>https://other.example/page</loc></url>
                <url><loc>https://example.com/image.jpg</loc></url>
                </urlset>""",
            ),
        }
    )

    result = estimate_public_website("https://example.com/", transport=transport)

    assert result.method == "sitemap"
    assert result.confidence == "high"
    assert result.estimated_pages == 2
    assert result.package == "small"
    assert result.sitemap_documents == 1


def test_estimate_falls_back_to_bounded_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.public_estimate.validate_public_http_url", lambda _: None)
    transport = _transport(
        {
            "https://example.com/": (
                200,
                "text/html",
                '<a href="/about">Over</a><a href="https://other.example/page">Extern</a>',
            ),
            "https://example.com/about": (200, "text/html", '<a href="/contact">Contact</a>'),
            "https://example.com/contact": (200, "text/html", "<p>Contact</p>"),
        }
    )

    result = estimate_public_website("https://example.com/", transport=transport)

    assert result.method == "sample"
    assert result.confidence == "low"
    assert result.estimated_pages == 3
    assert result.package == "small"


@pytest.mark.parametrize(
    ("pages", "expected"),
    [(100, "small"), (101, "growth"), (1_001, "large"), (10_001, "custom")],
)
def test_package_boundaries(pages: int, expected: str) -> None:
    assert package_for_pages(pages) == expected


def test_public_estimate_rate_limit() -> None:
    _requests.clear()
    for _ in range(5):
        _enforce_rate_limit("test-client")
    with pytest.raises(HTTPException) as exc_info:
        _enforce_rate_limit("test-client")
    assert exc_info.value.status_code == 429

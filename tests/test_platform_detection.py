from app.services.http_crawler import FetchResult
from app.services.platform_detection import detect_platform


def result(html: str, headers: dict[str, str] | None = None) -> FetchResult:
    return FetchResult(
        requested_url="https://example.com/",
        final_url="https://example.com/",
        status_code=200,
        redirect_chain=[],
        headers=headers or {"content-type": "text/html"},
        content=html.encode(),
        response_time_ms=10,
    )


def test_detects_wordpress_from_multiple_independent_signals() -> None:
    detection = detect_platform(
        result('<meta name="generator" content="WordPress 6"><script src="/wp-includes/a.js">')
    )
    assert detection.platform == "wordpress"
    assert detection.confidence == "high"


def test_detects_shopify_from_single_signal_with_medium_confidence() -> None:
    detection = detect_platform(result('<script src="https://cdn.shopify.com/theme.js">'))
    assert detection.platform == "shopify"
    assert detection.confidence == "medium"


def test_returns_unknown_without_recognized_signals() -> None:
    detection = detect_platform(result("<html><body>Maatwerk</body></html>"))
    assert detection.platform is None
    assert detection.confidence is None

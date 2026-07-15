import httpx
import pytest

from app.services.http_crawler import CrawlError, fetch_metadata, fetch_url
from app.services.url_normalization import InvalidUrlError


@pytest.fixture(autouse=True)
def permit_mock_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.http_crawler.validate_public_http_url", lambda _: None)


def test_follows_redirect_chain() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<h1>New</h1>")

    result = fetch_url("https://example.com/old", transport=httpx.MockTransport(handler))
    assert result.status_code == 200
    assert result.final_url == "https://example.com/new"
    assert len(result.redirect_chain) == 1


def test_detects_redirect_loop() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        target = "/b" if request.url.path == "/a" else "/a"
        return httpx.Response(302, headers={"location": target})

    with pytest.raises(CrawlError, match="loop") as exc_info:
        fetch_url("https://example.com/a", transport=httpx.MockTransport(handler))
    assert exc_info.value.error_type == "redirect_loop"


def test_classifies_timeout() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Timed out")

    with pytest.raises(CrawlError, match="Timed out") as exc_info:
        fetch_url("https://example.com", transport=httpx.MockTransport(handler))

    assert exc_info.value.error_type == "timeout"


def test_limits_response_size() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 11))
    with pytest.raises(CrawlError, match="maximum size"):
        fetch_url("https://example.com", max_response_size=10, transport=transport)


def test_fetch_metadata_uses_head_without_downloading_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "HEAD"
        return httpx.Response(
            200,
            headers={"Content-Type": "application/pdf", "Content-Length": "7500000"},
            content=b"body that must not be consumed",
        )

    result = fetch_metadata("https://example.com/file.pdf", transport=httpx.MockTransport(handler))
    assert result.status_code == 200
    assert result.headers["content-length"] == "7500000"


def test_unresolvable_hostname_is_a_recoverable_crawl_error(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fail_resolution(*_: object, **__: object) -> object:
        raise InvalidUrlError("Hostname could not be resolved")

    monkeypatch.setattr("app.services.http_crawler.validate_public_http_url", fail_resolution)

    with pytest.raises(CrawlError) as captured:
        fetch_url("http://human.nl/alvriend")

    assert captured.value.error_type == "invalid_target"
    assert str(captured.value) == "Hostname could not be resolved"

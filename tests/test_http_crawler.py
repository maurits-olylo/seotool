import httpx
import pytest

from app.services.http_crawler import CrawlError, fetch_url


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

    with pytest.raises(CrawlError, match="loop"):
        fetch_url("https://example.com/a", transport=httpx.MockTransport(handler))


def test_limits_response_size() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 11))
    with pytest.raises(CrawlError, match="maximum size"):
        fetch_url("https://example.com", max_response_size=10, transport=transport)

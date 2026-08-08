from dataclasses import dataclass

from app.services import browser_renderer


def test_renderer_blocks_private_and_heavy_requests(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def validate(url: str) -> None:
        if "private.test" in url:
            raise browser_renderer.InvalidUrlError("private")

    monkeypatch.setattr(browser_renderer, "validate_public_http_url", validate)
    playwright = _PlaywrightFactory(
        [
            _Request("https://example.com/", "document"),
            _Request("https://private.test/data", "fetch"),
            _Request("https://example.com/hero.jpg", "image"),
            _Request("data:text/plain,ok", "other"),
        ]
    )

    result = browser_renderer.render_page_html(
        "https://example.com/", playwright_factory=playwright
    )

    assert result.browser_name == "chromium"
    assert result.request_count == 4
    assert playwright.routes == ["continue", "abort", "abort", "continue"]
    assert playwright.context_options["service_workers"] == "block"
    assert playwright.context_options["accept_downloads"] is False
    assert result.element_boxes == [
        {
            "element_type": "a",
            "element_id": "cta",
            "target_url": "https://example.com/contact",
            "visible_text": "Contact",
            "occurrence_index": 1,
            "x": 20,
            "y": 30,
            "width": 120,
            "height": 40,
        }
    ]


def test_renderer_enforces_request_limit(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(browser_renderer, "MAX_BROWSER_REQUESTS", 2)
    monkeypatch.setattr(browser_renderer, "validate_public_http_url", lambda _url: None)
    playwright = _PlaywrightFactory(
        [_Request(f"https://example.com/{number}.js", "script") for number in range(3)]
    )

    browser_renderer.render_page_html("https://example.com/", playwright_factory=playwright)

    assert playwright.routes == ["continue", "continue", "abort"]


@dataclass
class _Request:
    url: str
    resource_type: str


class _Route:
    def __init__(self, request: _Request, outcomes: list[str]) -> None:
        self.request = request
        self.outcomes = outcomes

    def abort(self, _reason: str) -> None:
        self.outcomes.append("abort")

    def continue_(self) -> None:
        self.outcomes.append("continue")


class _Page:
    url = "https://example.com/"

    def __init__(self, owner, requests) -> None:  # type: ignore[no-untyped-def]
        self.owner = owner
        self.requests = requests
        self.handler = None

    def set_default_timeout(self, _timeout: int) -> None:
        pass

    def route(self, _pattern: str, handler) -> None:  # type: ignore[no-untyped-def]
        self.handler = handler

    def goto(self, _url: str, **_kwargs):  # type: ignore[no-untyped-def]
        for request in self.requests:
            self.handler(_Route(request, self.owner.routes))
        return object()

    def wait_for_timeout(self, _timeout: int) -> None:
        pass

    def content(self) -> str:
        return "<html><body><main>Rendered</main></body></html>"

    def screenshot(self, **_kwargs) -> bytes:  # type: ignore[no-untyped-def]
        return b"png"

    def locator(self, _selector: str):  # type: ignore[no-untyped-def]
        return _Locator()


class _Locator:
    def evaluate_all(self, _script: str) -> list[dict[str, object]]:
        return [
            {
                "element_type": "a",
                "element_id": "cta",
                "target_url": "https://example.com/contact",
                "visible_text": "Contact",
                "occurrence_index": 1,
                "x": 20,
                "y": 30,
                "width": 120,
                "height": 40,
            }
        ]


class _Context:
    def __init__(self, owner, requests) -> None:  # type: ignore[no-untyped-def]
        self.owner = owner
        self.requests = requests

    def new_page(self):  # type: ignore[no-untyped-def]
        return _Page(self.owner, self.requests)

    def close(self) -> None:
        pass


class _Browser:
    def __init__(self, owner, requests) -> None:  # type: ignore[no-untyped-def]
        self.owner = owner
        self.requests = requests

    def new_context(self, **kwargs):  # type: ignore[no-untyped-def]
        self.owner.context_options = kwargs
        return _Context(self.owner, self.requests)

    def close(self) -> None:
        pass


class _Chromium:
    def __init__(self, owner, requests) -> None:  # type: ignore[no-untyped-def]
        self.owner = owner
        self.requests = requests

    def launch(self, **_kwargs):  # type: ignore[no-untyped-def]
        return _Browser(self.owner, self.requests)


class _Playwright:
    def __init__(self, owner, requests) -> None:  # type: ignore[no-untyped-def]
        self.chromium = _Chromium(owner, requests)


class _PlaywrightContext:
    def __init__(self, owner, requests) -> None:  # type: ignore[no-untyped-def]
        self.playwright = _Playwright(owner, requests)

    def __enter__(self):  # type: ignore[no-untyped-def]
        return self.playwright

    def __exit__(self, *_args) -> None:  # type: ignore[no-untyped-def]
        pass


class _PlaywrightFactory:
    def __init__(self, requests) -> None:  # type: ignore[no-untyped-def]
        self.requests = requests
        self.routes: list[str] = []
        self.context_options: dict[str, object] = {}

    def __call__(self):  # type: ignore[no-untyped-def]
        return _PlaywrightContext(self, self.requests)

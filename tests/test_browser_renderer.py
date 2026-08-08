from dataclasses import dataclass

from app.services import browser_renderer
from app.services.staging_render_acceptance import STAGING_RENDER_ACCEPTANCE_URL


def test_renderer_allows_only_exact_internal_acceptance_page_in_staging(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "app.core.config.get_settings", lambda: type("Settings", (), {"app_env": "staging"})()
    )
    browser_renderer._validate_render_url(STAGING_RENDER_ACCEPTANCE_URL)

    def reject(_url: str) -> None:
        raise browser_renderer.InvalidUrlError("private")

    monkeypatch.setattr(browser_renderer, "validate_public_http_url", reject)
    with __import__("pytest").raises(browser_renderer.InvalidUrlError):
        browser_renderer._validate_render_url(f"{STAGING_RENDER_ACCEPTANCE_URL}/other")


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


def test_renderer_focuses_reliable_issue_target_before_screenshot(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(browser_renderer, "validate_public_http_url", lambda _url: None)
    playwright = _PlaywrightFactory([])

    result = browser_renderer.render_page_html(
        "https://example.com/",
        focus_target={"strategy": "id", "value": "cta"},
        playwright_factory=playwright,
    )

    assert result.focus_applied is True
    assert result.focus_status == "focused"
    assert playwright.focus_targets == [{"strategy": "id", "value": "cta"}]
    assert playwright.capture_events == ["focus", "geometry", "screenshot"]


def test_renderer_ignores_invalid_focus_without_failing(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(browser_renderer, "validate_public_http_url", lambda _url: None)
    playwright = _PlaywrightFactory([])

    result = browser_renderer.render_page_html(
        "https://example.com/",
        focus_target={"strategy": "xpath", "value": "/html/body/a"},
        playwright_factory=playwright,
    )

    assert result.focus_applied is False
    assert result.focus_status == "invalid"
    assert playwright.focus_targets == []


def test_renderer_reports_ambiguous_focus(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(browser_renderer, "validate_public_http_url", lambda _url: None)
    playwright = _PlaywrightFactory([], focus_match_count=2)

    result = browser_renderer.render_page_html(
        "https://example.com/",
        focus_target={"strategy": "text", "value": "Meer"},
        playwright_factory=playwright,
    )

    assert result.focus_status == "ambiguous"
    assert result.focus_applied is False


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
        self.owner.capture_events.append("screenshot")
        return b"png"

    def evaluate(self, _script: str, target: dict[str, object]) -> int:
        self.owner.capture_events.append("focus")
        self.owner.focus_targets.append(target)
        return self.owner.focus_match_count

    def locator(self, _selector: str):  # type: ignore[no-untyped-def]
        return _Locator(self.owner)


class _Locator:
    def __init__(self, owner) -> None:  # type: ignore[no-untyped-def]
        self.owner = owner

    def evaluate_all(self, _script: str) -> list[dict[str, object]]:
        self.owner.capture_events.append("geometry")
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
    def __init__(self, requests, *, focus_match_count: int = 1) -> None:  # type: ignore[no-untyped-def]
        self.requests = requests
        self.routes: list[str] = []
        self.context_options: dict[str, object] = {}
        self.focus_targets: list[dict[str, object]] = []
        self.capture_events: list[str] = []
        self.focus_match_count = focus_match_count

    def __call__(self):  # type: ignore[no-untyped-def]
        return _PlaywrightContext(self, self.requests)

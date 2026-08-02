from dataclasses import dataclass
from typing import Any

from app.services.security import validate_public_http_url
from app.services.url_normalization import InvalidUrlError

MAX_BROWSER_REQUESTS = 100
MAX_RENDERED_HTML_BYTES = 5_000_000
BLOCKED_RESOURCE_TYPES = {"font", "image", "media"}


class RenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class BrowserRenderResult:
    html: str
    browser_name: str
    request_count: int


def render_page_html(
    url: str,
    *,
    timeout_seconds: int = 20,
    settle_time_ms: int = 1_000,
    playwright_factory: Any | None = None,
) -> BrowserRenderResult:
    """Render one public page in an isolated context with bounded network activity."""
    validate_public_http_url(url)
    if playwright_factory is None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RenderError("Playwright is not installed in this worker") from exc
        playwright_factory = sync_playwright

    request_count = 0
    try:
        with playwright_factory() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                accept_downloads=False,
                java_script_enabled=True,
                service_workers="block",
                viewport={"width": 1365, "height": 768},
            )
            page = context.new_page()
            page.set_default_timeout(timeout_seconds * 1_000)

            def route_request(route: Any) -> None:
                nonlocal request_count
                request_count += 1
                request = route.request
                if request_count > MAX_BROWSER_REQUESTS:
                    route.abort("blockedbyclient")
                    return
                if request.resource_type in BLOCKED_RESOURCE_TYPES:
                    route.abort("blockedbyclient")
                    return
                if request.url.startswith(("data:", "blob:")):
                    route.continue_()
                    return
                try:
                    validate_public_http_url(request.url)
                except InvalidUrlError:
                    route.abort("blockedbyclient")
                    return
                route.continue_()

            page.route("**/*", route_request)
            response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=timeout_seconds * 1_000,
            )
            if response is None:
                raise RenderError("Browser navigation returned no response")
            page.wait_for_timeout(min(max(settle_time_ms, 0), 2_000))
            html = page.content()
            final_url = page.url
            context.close()
            browser.close()
    except RenderError:
        raise
    except Exception as exc:
        raise RenderError(f"Browser rendering failed: {type(exc).__name__}") from exc

    validate_public_http_url(final_url)
    if len(html.encode("utf-8")) > MAX_RENDERED_HTML_BYTES:
        raise RenderError("Rendered HTML exceeds maximum size")
    return BrowserRenderResult(html=html, browser_name="chromium", request_count=request_count)

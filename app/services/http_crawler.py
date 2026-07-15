import time
from dataclasses import dataclass

import httpx

from app.services.security import validate_public_http_url
from app.services.url_normalization import InvalidUrlError


class CrawlError(RuntimeError):
    def __init__(self, message: str, *, error_type: str = "request_failed") -> None:
        super().__init__(message)
        self.error_type = error_type


@dataclass(frozen=True)
class FetchResult:
    requested_url: str
    final_url: str
    status_code: int
    redirect_chain: list[dict[str, object]]
    headers: dict[str, str]
    content: bytes
    response_time_ms: int


@dataclass(frozen=True)
class FetchMetadata:
    requested_url: str
    final_url: str
    status_code: int
    redirect_chain: list[dict[str, object]]
    headers: dict[str, str]
    response_time_ms: int


def fetch_url(
    url: str,
    *,
    timeout_seconds: int = 20,
    max_response_size: int = 5_000_000,
    max_redirects: int = 10,
    user_agent: str = "SEO-Monitor-Bot/0.1",
    transport: httpx.BaseTransport | None = None,
) -> FetchResult:
    _validate_target(url)
    started = time.monotonic()
    chain: list[dict[str, object]] = []
    current_url = url
    with httpx.Client(
        timeout=timeout_seconds,
        follow_redirects=False,
        headers={"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml"},
        transport=transport,
    ) as client:
        for _ in range(max_redirects + 1):
            _validate_target(current_url)
            try:
                with client.stream("GET", current_url) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise CrawlError(
                                "Redirect without Location header",
                                error_type="redirect_invalid",
                            )
                        next_url = str(response.url.join(location))
                        chain.append(
                            {
                                "url": current_url,
                                "status_code": response.status_code,
                                "target": next_url,
                            }
                        )
                        if next_url in {item["url"] for item in chain}:
                            raise CrawlError("Redirect loop detected", error_type="redirect_loop")
                        current_url = next_url
                        continue
                    content = _read_limited(response, max_response_size)
                    return FetchResult(
                        requested_url=url,
                        final_url=str(response.url),
                        status_code=response.status_code,
                        redirect_chain=chain,
                        headers={key.lower(): value for key, value in response.headers.items()},
                        content=content,
                        response_time_ms=round((time.monotonic() - started) * 1000),
                    )
            except httpx.TimeoutException as exc:
                raise CrawlError(str(exc), error_type="timeout") from exc
            except httpx.HTTPError as exc:
                raise CrawlError(str(exc)) from exc
    raise CrawlError("Redirect chain exceeds maximum length", error_type="redirect_limit")


def fetch_metadata(
    url: str,
    *,
    timeout_seconds: int = 20,
    max_redirects: int = 10,
    user_agent: str = "SEO-Monitor-Bot/0.1",
    transport: httpx.BaseTransport | None = None,
) -> FetchMetadata:
    _validate_target(url)
    started = time.monotonic()
    chain: list[dict[str, object]] = []
    current_url = url
    with httpx.Client(
        timeout=timeout_seconds,
        follow_redirects=False,
        headers={"User-Agent": user_agent, "Accept": "*/*"},
        transport=transport,
    ) as client:
        for _ in range(max_redirects + 1):
            _validate_target(current_url)
            try:
                response = client.head(current_url)
            except httpx.TimeoutException as exc:
                raise CrawlError(str(exc), error_type="timeout") from exc
            except httpx.HTTPError as exc:
                raise CrawlError(str(exc)) from exc
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise CrawlError(
                        "Redirect without Location header",
                        error_type="redirect_invalid",
                    )
                next_url = str(response.url.join(location))
                chain.append(
                    {
                        "url": current_url,
                        "status_code": response.status_code,
                        "target": next_url,
                    }
                )
                if next_url in {item["url"] for item in chain}:
                    raise CrawlError("Redirect loop detected", error_type="redirect_loop")
                current_url = next_url
                continue
            return FetchMetadata(
                requested_url=url,
                final_url=str(response.url),
                status_code=response.status_code,
                redirect_chain=chain,
                headers={key.lower(): value for key, value in response.headers.items()},
                response_time_ms=round((time.monotonic() - started) * 1000),
            )
    raise CrawlError("Redirect chain exceeds maximum length", error_type="redirect_limit")


def _read_limited(response: httpx.Response, maximum: int) -> bytes:
    declared = response.headers.get("content-length")
    if declared and int(declared) > maximum:
        raise CrawlError("Response exceeds maximum size")
    content = bytearray()
    for chunk in response.iter_bytes():
        content.extend(chunk)
        if len(content) > maximum:
            raise CrawlError("Response exceeds maximum size")
    return bytes(content)


def _validate_target(url: str) -> None:
    try:
        validate_public_http_url(url)
    except InvalidUrlError as exc:
        raise CrawlError(str(exc), error_type="invalid_target") from exc

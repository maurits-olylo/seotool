import time
from dataclasses import dataclass

import httpx

from app.services.security import validate_public_http_url


class CrawlError(RuntimeError):
    pass


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
    validate_public_http_url(url)
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
            validate_public_http_url(current_url)
            try:
                with client.stream("GET", current_url) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise CrawlError("Redirect without Location header")
                        next_url = str(response.url.join(location))
                        chain.append(
                            {
                                "url": current_url,
                                "status_code": response.status_code,
                                "target": next_url,
                            }
                        )
                        if next_url in {item["url"] for item in chain}:
                            raise CrawlError("Redirect loop detected")
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
            except httpx.HTTPError as exc:
                raise CrawlError(str(exc)) from exc
    raise CrawlError("Redirect chain exceeds maximum length")


def fetch_metadata(
    url: str,
    *,
    timeout_seconds: int = 20,
    max_redirects: int = 10,
    user_agent: str = "SEO-Monitor-Bot/0.1",
    transport: httpx.BaseTransport | None = None,
) -> FetchMetadata:
    validate_public_http_url(url)
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
            validate_public_http_url(current_url)
            try:
                response = client.head(current_url)
            except httpx.HTTPError as exc:
                raise CrawlError(str(exc)) from exc
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise CrawlError("Redirect without Location header")
                next_url = str(response.url.join(location))
                chain.append(
                    {
                        "url": current_url,
                        "status_code": response.status_code,
                        "target": next_url,
                    }
                )
                if next_url in {item["url"] for item in chain}:
                    raise CrawlError("Redirect loop detected")
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
    raise CrawlError("Redirect chain exceeds maximum length")


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

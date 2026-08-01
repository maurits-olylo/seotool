from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import monotonic
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.services.security import validate_public_http_url
from app.services.sitemap import InvalidSitemapError, parse_sitemap
from app.services.url_filtering import is_probable_html_page
from app.services.url_normalization import InvalidUrlError, normalize_url
from app.services.url_scope import is_url_in_website_scope

MAX_SITEMAP_DOCUMENTS = 10
MAX_ESTIMATED_URLS = 10_001
MAX_SAMPLE_PAGES = 10
MAX_SAMPLE_URLS = 100
MAX_RESPONSE_SIZE = 5_000_000
MAX_ESTIMATE_SECONDS = 20


class PublicEstimateError(RuntimeError):
    pass


@dataclass(frozen=True)
class PublicEstimate:
    normalized_url: str
    estimated_pages: int
    package: str
    method: str
    confidence: str
    sitemap_documents: int
    capped: bool
    explanation: str


def estimate_public_website(
    raw_url: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> PublicEstimate:
    try:
        normalized = normalize_url(raw_url)
        validate_public_http_url(normalized)
    except InvalidUrlError as exc:
        raise PublicEstimateError(str(exc)) from exc

    deadline = monotonic() + MAX_ESTIMATE_SECONDS
    robots_url = urljoin(normalized, "/robots.txt")
    robots_text = _fetch_text(
        robots_url,
        base_url=normalized,
        maximum=1_000_000,
        deadline=deadline,
        transport=transport,
    )
    sitemap_urls = _robots_sitemaps(robots_text)
    if not sitemap_urls:
        sitemap_urls = [urljoin(normalized, "/sitemap.xml")]
    estimate = _estimate_from_sitemaps(
        normalized, sitemap_urls, deadline=deadline, transport=transport
    )
    if estimate is not None:
        return estimate
    return _estimate_from_sample(normalized, deadline=deadline, transport=transport)


def package_for_pages(pages: int) -> str:
    if pages <= 100:
        return "small"
    if pages <= 1_000:
        return "growth"
    if pages <= 10_000:
        return "large"
    return "custom"


def _estimate_from_sitemaps(
    base_url: str,
    roots: list[str],
    *,
    deadline: float,
    transport: httpx.BaseTransport | None,
) -> PublicEstimate | None:
    pending = deque(dict.fromkeys(roots))
    visited: set[str] = set()
    urls: set[str] = set()
    while pending and len(visited) < MAX_SITEMAP_DOCUMENTS and len(urls) < MAX_ESTIMATED_URLS:
        sitemap_url = pending.popleft()
        if sitemap_url in visited or not is_url_in_website_scope(sitemap_url, base_url=base_url):
            continue
        visited.add(sitemap_url)
        content = _fetch_bytes(
            sitemap_url,
            base_url=base_url,
            maximum=MAX_RESPONSE_SIZE,
            deadline=deadline,
            transport=transport,
        )
        if content is None:
            continue
        try:
            document = parse_sitemap(content)
        except InvalidSitemapError:
            continue
        pending.extend(document.child_sitemaps)
        for item in document.urls:
            if not is_url_in_website_scope(item.location, base_url=base_url):
                continue
            try:
                candidate = normalize_url(item.location)
            except InvalidUrlError:
                continue
            if is_probable_html_page(candidate):
                urls.add(candidate)
            if len(urls) >= MAX_ESTIMATED_URLS:
                break
    if not urls:
        return None
    capped = len(urls) >= MAX_ESTIMATED_URLS or bool(pending)
    count = len(urls)
    return PublicEstimate(
        normalized_url=base_url,
        estimated_pages=count,
        package=package_for_pages(count),
        method="sitemap",
        confidence="high" if not capped else "medium",
        sitemap_documents=len(visited),
        capped=capped,
        explanation=(
            "Schatting op basis van unieke interne HTML-URL's uit openbare sitemaps."
            if not capped
            else "De openbare sitemapmeting bereikte de veiligheidslimiet; maatwerk is aanbevolen."
        ),
    )


def _estimate_from_sample(
    base_url: str, *, deadline: float, transport: httpx.BaseTransport | None
) -> PublicEstimate:
    pending = deque([base_url])
    visited: set[str] = set()
    discovered: set[str] = {base_url}
    while pending and len(visited) < MAX_SAMPLE_PAGES and len(discovered) < MAX_SAMPLE_URLS:
        url = pending.popleft()
        if url in visited:
            continue
        visited.add(url)
        content = _fetch_bytes(
            url,
            base_url=base_url,
            maximum=MAX_RESPONSE_SIZE,
            deadline=deadline,
            transport=transport,
        )
        if not content:
            continue
        soup = BeautifulSoup(content, "lxml")
        for anchor in soup.select("a[href]"):
            try:
                candidate = normalize_url(str(anchor.get("href")), base_url=url)
            except InvalidUrlError:
                continue
            if not is_url_in_website_scope(candidate, base_url=base_url):
                continue
            if not is_probable_html_page(candidate):
                continue
            if candidate not in discovered:
                discovered.add(candidate)
                pending.append(candidate)
            if len(discovered) >= MAX_SAMPLE_URLS:
                break
    count = len(discovered)
    return PublicEstimate(
        normalized_url=base_url,
        estimated_pages=count,
        package=package_for_pages(count),
        method="sample",
        confidence="low",
        sitemap_documents=0,
        capped=len(discovered) >= MAX_SAMPLE_URLS or bool(pending),
        explanation=(
            "Lage-zekerheidsschatting uit een begrensde openbare steekproef; na verificatie volgt "
            "het definitieve volume."
        ),
    )


def _robots_sitemaps(content: str | None) -> list[str]:
    if not content:
        return []
    values: list[str] = []
    for line in content.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip().lower() == "sitemap" and value.strip():
            values.append(value.strip())
    return values


def _fetch_text(
    url: str,
    *,
    base_url: str,
    maximum: int,
    deadline: float,
    transport: httpx.BaseTransport | None,
) -> str | None:
    content = _fetch_bytes(
        url,
        base_url=base_url,
        maximum=maximum,
        deadline=deadline,
        transport=transport,
    )
    return content.decode("utf-8", errors="replace") if content is not None else None


def _fetch_bytes(
    url: str,
    *,
    base_url: str,
    maximum: int,
    deadline: float,
    transport: httpx.BaseTransport | None,
) -> bytes | None:
    current = url
    with httpx.Client(timeout=5, follow_redirects=False, transport=transport) as client:
        for _ in range(4):
            if monotonic() >= deadline:
                raise PublicEstimateError("Public estimate exceeded the total time limit")
            try:
                validate_public_http_url(current)
            except InvalidUrlError as exc:
                raise PublicEstimateError(str(exc)) from exc
            if not is_url_in_website_scope(current, base_url=base_url):
                raise PublicEstimateError("Redirect or source falls outside the requested website")
            try:
                with client.stream("GET", current, headers={"Accept": "*/*"}) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            return None
                        current = str(response.url.join(location))
                        continue
                    if response.status_code != 200:
                        return None
                    declared = response.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > maximum:
                        raise PublicEstimateError("Response exceeds the public estimate limit")
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        if monotonic() >= deadline:
                            raise PublicEstimateError(
                                "Public estimate exceeded the total time limit"
                            )
                        content.extend(chunk)
                        if len(content) > maximum:
                            raise PublicEstimateError("Response exceeds the public estimate limit")
                    return bytes(content)
            except httpx.HTTPError:
                return None
    raise PublicEstimateError("Redirect chain exceeds the public estimate limit")

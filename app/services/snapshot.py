from urllib.parse import urlsplit, urlunsplit

import structlog
from sqlalchemy.orm import Session

from app.models.crawl import ElementLocation, UrlLink, UrlSnapshot
from app.models.discovery import Url
from app.models.website import Website
from app.services.html_extraction import extract_page
from app.services.http_crawler import FetchResult
from app.services.url_normalization import InvalidUrlError, normalize_url
from app.services.url_registry import register_url
from app.services.url_scope import is_url_in_website_scope

logger = structlog.get_logger()


def store_fetch_result(
    db: Session, *, url: Url, crawl_run_id: object, result: FetchResult
) -> UrlSnapshot:
    content_type = result.headers.get("content-type", "").split(";", 1)[0].lower()
    page = None
    if content_type in {"text/html", "application/xhtml+xml"}:
        encoding = _charset(result.headers.get("content-type"))
        page = extract_page(result.content.decode(encoding, errors="replace"), result.final_url)

    x_robots = result.headers.get("x-robots-tag")
    robots_values = " ".join(filter(None, [page.meta_robots if page else None, x_robots])).lower()
    is_indexable = result.status_code == 200 and "noindex" not in robots_values
    snapshot = UrlSnapshot(
        url_id=url.id,
        crawl_run_id=crawl_run_id,
        requested_url=result.requested_url,
        final_url=result.final_url,
        status_code=result.status_code,
        redirect_chain=result.redirect_chain,
        content_type=content_type or None,
        response_time_ms=result.response_time_ms,
        response_size=len(result.content),
        etag=result.headers.get("etag"),
        last_modified=result.headers.get("last-modified"),
        title=page.title if page else None,
        meta_description=page.meta_description if page else None,
        canonical=page.canonical if page else None,
        meta_robots=page.meta_robots if page else None,
        x_robots_tag=x_robots,
        html_lang=page.html_lang if page else None,
        headings=page.headings if page else {},
        word_count=page.word_count if page else None,
        main_content=page.main_content if page else None,
        schema_types=page.schema_types if page else [],
        schema_data=page.schema_data if page else [],
        html_hash=page.html_hash if page else None,
        main_content_hash=page.main_content_hash if page else None,
        metadata_hash=page.metadata_hash if page else None,
        links_hash=page.links_hash if page else None,
        schema_hash=page.schema_hash if page else None,
        is_indexable=is_indexable,
    )
    db.add(snapshot)
    db.flush()
    url.current_status_code = result.status_code
    url.current_final_url = normalize_url(result.final_url)
    url.is_indexable = is_indexable
    if page:
        website = db.get(Website, url.website_id)
        allowed_subdomains = (
            website.settings.allowed_subdomains if website and website.settings else []
        )
        for link in page.links:
            try:
                normalized_target = normalize_url(link.target_url)
            except InvalidUrlError as exc:
                logger.warning(
                    "crawl_link_skipped_invalid_url",
                    website_id=str(url.website_id),
                    crawl_run_id=str(crawl_run_id),
                    source_url=_safe_url_for_log(url.normalized_url),
                    target_url=_safe_url_for_log(link.target_url),
                    error=str(exc),
                )
                continue
            target = None
            is_internal = bool(
                website
                and is_url_in_website_scope(
                    normalized_target,
                    base_url=website.base_url,
                    allowed_subdomains=allowed_subdomains,
                )
            )
            if is_internal:
                target = register_url(
                    db,
                    website_id=url.website_id,
                    raw_url=normalized_target,
                    source_type="internal_link",
                    source_url=url.normalized_url,
                )
            db.add(
                UrlLink(
                    crawl_run_id=crawl_run_id,
                    source_url_id=url.id,
                    target_url=normalized_target,
                    target_url_id=target.id if target else None,
                    anchor_text=link.anchor_text,
                    is_internal=is_internal,
                    is_nofollow=link.is_nofollow,
                )
            )
        for element in page.elements:
            db.add(
                ElementLocation(
                    website_id=url.website_id,
                    source_url_id=url.id,
                    snapshot_id=snapshot.id,
                    crawl_run_id=crawl_run_id,
                    issue_types=element.issue_types,
                    element_type=element.element_type,
                    target_url=element.target_url,
                    visible_text=element.visible_text,
                    element_id=element.element_id,
                    css_selector=element.css_selector,
                    xpath=element.xpath,
                    html_fragment=element.html_fragment,
                    occurrence_index=element.occurrence_index,
                    text_prefix=element.text_prefix,
                    text_suffix=element.text_suffix,
                    text_is_unique=element.text_is_unique,
                    context_is_unique=element.context_is_unique,
                    rendered_dynamically=element.rendered_dynamically,
                )
            )
            if element.element_type == "img" and element.target_url:
                try:
                    normalized_image = normalize_url(element.target_url)
                except InvalidUrlError:
                    continue
                if website and is_url_in_website_scope(
                    normalized_image,
                    base_url=website.base_url,
                    allowed_subdomains=allowed_subdomains,
                ):
                    register_url(
                        db,
                        website_id=url.website_id,
                        raw_url=normalized_image,
                        source_type="internal_link",
                        source_url=url.normalized_url,
                    )
    from app.services.analysis import analyze_snapshot

    analyze_snapshot(db, snapshot)
    return snapshot


def _charset(content_type: str | None) -> str:
    if content_type and "charset=" in content_type.lower():
        return content_type.lower().split("charset=", 1)[1].split(";", 1)[0].strip()
    return "utf-8"


def _safe_url_for_log(value: str) -> str:
    parts = urlsplit(value)
    netloc = parts.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))[:1000]

from sqlalchemy.orm import Session

from app.models.crawl import UrlLink, UrlSnapshot
from app.models.discovery import Url
from app.services.html_extraction import extract_page
from app.services.http_crawler import FetchResult
from app.services.url_normalization import normalize_url
from app.services.url_registry import register_url


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
        for link in page.links:
            target = None
            if link.is_internal:
                target = register_url(
                    db,
                    website_id=url.website_id,
                    raw_url=link.target_url,
                    source_type="internal_link",
                    source_url=url.normalized_url,
                )
            db.add(
                UrlLink(
                    crawl_run_id=crawl_run_id,
                    source_url_id=url.id,
                    target_url=normalize_url(link.target_url),
                    target_url_id=target.id if target else None,
                    anchor_text=link.anchor_text,
                    is_internal=link.is_internal,
                    is_nofollow=link.is_nofollow,
                )
            )
    from app.services.analysis import analyze_snapshot

    analyze_snapshot(db, snapshot)
    return snapshot


def _charset(content_type: str | None) -> str:
    if content_type and "charset=" in content_type.lower():
        return content_type.lower().split("charset=", 1)[1].split(";", 1)[0].strip()
    return "utf-8"

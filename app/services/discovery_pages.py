from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crawl import UrlSnapshot
from app.models.discovery import Url
from app.services.url_normalization import InvalidUrlError, normalize_url

FUNCTIONAL_SEARCH_PATHS = {"/search", "/zoeken"}


def is_discovery_only_page(page_url: str, canonical: str | None) -> bool:
    """Return true for functional search pages and consolidated query variants."""
    try:
        page = urlsplit(normalize_url(page_url))
    except (InvalidUrlError, ValueError):
        return False
    if page.path.rstrip("/").casefold() in FUNCTIONAL_SEARCH_PATHS:
        return True
    if not canonical:
        return False
    try:
        target = urlsplit(normalize_url(canonical))
    except (InvalidUrlError, ValueError):
        return False
    return bool(
        page.query
        and not target.query
        and (page.scheme, page.netloc, page.path) == (target.scheme, target.netloc, target.path)
    )


def is_discovery_only_snapshot(url: Url, snapshot: UrlSnapshot) -> bool:
    return is_discovery_only_page(url.normalized_url, snapshot.canonical)


def discovery_only_url_ids(
    db: Session,
    *,
    website_id: object,
    crawl_run_id: object,
) -> set[object]:
    rows = db.execute(
        select(Url, UrlSnapshot)
        .join(UrlSnapshot, UrlSnapshot.url_id == Url.id)
        .where(
            Url.website_id == website_id,
            UrlSnapshot.crawl_run_id == crawl_run_id,
        )
    )
    return {url.id for url, snapshot in rows if is_discovery_only_snapshot(url, snapshot)}

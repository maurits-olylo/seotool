from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.common import utc_now
from app.models.discovery import Url, UrlSource
from app.services.url_normalization import NormalizationOptions, normalize_url


def register_url(
    db: Session,
    *,
    website_id: object,
    raw_url: str,
    source_type: str,
    source_url: str = "",
    ignored_query_parameters: frozenset[str] = frozenset(),
) -> Url:
    normalized = normalize_url(
        raw_url,
        options=NormalizationOptions(ignored_query_parameters=ignored_query_parameters),
    )
    url = db.scalar(
        select(Url).where(Url.website_id == website_id, Url.normalized_url == normalized)
    )
    now = utc_now()
    if url is None:
        url = Url(website_id=website_id, normalized_url=normalized)
        db.add(url)
        db.flush()
    else:
        url.last_seen_at = now
        url.is_active = True

    source = db.scalar(
        select(UrlSource).where(
            UrlSource.url_id == url.id,
            UrlSource.source_type == source_type,
            UrlSource.source_url == source_url,
        )
    )
    if source is None:
        db.add(UrlSource(url_id=url.id, source_type=source_type, source_url=source_url))
    else:
        source.last_seen_at = now
    return url

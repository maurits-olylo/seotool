from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crawl import ElementLocation
from app.services.url_normalization import InvalidUrlError, normalize_url


def mark_target_elements_for_targets(
    db: Session,
    *,
    crawl_run_id: object,
    target_urls: Collection[str],
    issue_type: str,
    element_types: set[str] | None = None,
) -> int:
    """Mark matching elements without repeatedly scanning an entire crawl run."""
    normalized_targets = {_normalize_target(target_url) for target_url in target_urls}
    if not normalized_targets:
        return 0
    conditions = [
        ElementLocation.crawl_run_id == crawl_run_id,
        ElementLocation.target_url.is_not(None),
    ]
    if element_types:
        conditions.append(ElementLocation.element_type.in_(element_types))
    locations = db.scalars(
        select(ElementLocation).where(*conditions).execution_options(yield_per=1000)
    )
    updated = 0
    for location in locations:
        if location.target_url is None:
            continue
        if _normalize_target(location.target_url) not in normalized_targets:
            continue
        if issue_type not in location.issue_types:
            location.issue_types = [*location.issue_types, issue_type]
        updated += 1
    return updated


def mark_target_elements(
    db: Session,
    *,
    crawl_run_id: object,
    target_url: str,
    issue_type: str,
    element_types: set[str] | None = None,
) -> int:
    return mark_target_elements_for_targets(
        db,
        crawl_run_id=crawl_run_id,
        target_urls={target_url},
        issue_type=issue_type,
        element_types=element_types,
    )


def _normalize_target(target_url: str) -> str:
    try:
        return normalize_url(target_url)
    except InvalidUrlError:
        return target_url

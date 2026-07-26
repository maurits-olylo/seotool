from collections.abc import Callable, Collection

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
    check_control: Callable[[], None] | None = None,
    batch_size: int = 1000,
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
    updated = 0
    if check_control is None:
        locations = db.scalars(
            select(ElementLocation).where(*conditions).execution_options(yield_per=batch_size)
        )
        updated += _mark_locations(
            locations,
            normalized_targets=normalized_targets,
            issue_type=issue_type,
        )
        return updated

    last_id = None
    while True:
        batch_conditions = [*conditions]
        if last_id is not None:
            batch_conditions.append(ElementLocation.id > last_id)
        batch = list(
            db.scalars(
                select(ElementLocation)
                .where(*batch_conditions)
                .order_by(ElementLocation.id)
                .limit(batch_size)
            )
        )
        if not batch:
            break
        updated += _mark_locations(
            batch,
            normalized_targets=normalized_targets,
            issue_type=issue_type,
        )
        last_id = batch[-1].id
        db.flush()
        check_control()
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


def _mark_locations(
    locations: Collection[ElementLocation],
    *,
    normalized_targets: set[str],
    issue_type: str,
) -> int:
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

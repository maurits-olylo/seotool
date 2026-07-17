from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crawl import ElementLocation
from app.services.url_normalization import InvalidUrlError, normalize_url


def mark_target_elements(
    db: Session,
    *,
    crawl_run_id: object,
    target_url: str,
    issue_type: str,
    element_types: set[str] | None = None,
) -> int:
    try:
        normalized_target = normalize_url(target_url)
    except InvalidUrlError:
        normalized_target = target_url
    locations = list(
        db.scalars(
            select(ElementLocation).where(ElementLocation.crawl_run_id == crawl_run_id)
        )
    )
    updated = 0
    for location in locations:
        if element_types and location.element_type not in element_types:
            continue
        if not location.target_url:
            continue
        try:
            candidate = normalize_url(location.target_url)
        except InvalidUrlError:
            candidate = location.target_url
        if candidate != normalized_target:
            continue
        if issue_type not in location.issue_types:
            location.issue_types = [*location.issue_types, issue_type]
        updated += 1
    return updated

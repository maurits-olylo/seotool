"""Conservative lifecycle and freshness boundary for stored-data recalculation."""

from collections.abc import Iterator
from contextlib import contextmanager

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.crawl import UrlSnapshot
from app.models.discovery import Url

KEY = "stored_reanalysis"


@contextmanager
def stored_reanalysis(db: Session, *, website_id: object, source_run_id: object) -> Iterator[None]:
    ranked = (
        select(
            UrlSnapshot.url_id,
            UrlSnapshot.id,
            UrlSnapshot.crawl_run_id,
            func.row_number()
            .over(
                partition_by=UrlSnapshot.url_id,
                order_by=(UrlSnapshot.checked_at.desc(), UrlSnapshot.id.desc()),
            )
            .label("position"),
        )
        .join(Url, Url.id == UrlSnapshot.url_id)
        .where(Url.website_id == website_id)
        .subquery()
    )
    latest = {
        url_id: (snapshot_id, run_id)
        for url_id, snapshot_id, run_id in db.execute(
            select(ranked.c.url_id, ranked.c.id, ranked.c.crawl_run_id).where(
                ranked.c.position == 1
            )
        )
    }
    structlog.get_logger().info(
        "stored_reanalysis_started",
        website_id=str(website_id),
        source_run_id=str(source_run_id),
        latest_urls=len(latest),
        urls_outside_source_run=sum(run_id != source_run_id for _, run_id in latest.values()),
    )
    previous = db.info.get(KEY)
    db.info[KEY] = {
        "latest": latest,
        "source_run_id": source_run_id,
        "mixed_measurements": any(run_id != source_run_id for _, run_id in latest.values()),
    }
    try:
        yield
    finally:
        if previous is None:
            db.info.pop(KEY, None)
        else:
            db.info[KEY] = previous


def superseded_for_reanalysis(db: Session, *, url_id: object, snapshot_id: object) -> bool:
    context = db.info.get(KEY)
    if context is None:
        return False
    if url_id is None:
        # An older site-wide aggregate cannot establish a current finding.
        return bool(context["mixed_measurements"])
    latest = context["latest"].get(url_id)
    return latest is None or latest[0] != snapshot_id

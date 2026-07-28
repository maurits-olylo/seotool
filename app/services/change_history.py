from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.discovery import CrawlJob
from app.models.issues import Change
from app.models.website import Website

ACTIVE_CRAWL_STATUSES = {
    "pending",
    "running",
    "pause_requested",
    "paused",
    "cancel_requested",
}


@dataclass(frozen=True)
class ChangeHistoryReset:
    deleted: int
    website_id: str | None


def change_history_counts(db: Session) -> dict[str, object]:
    rows = db.execute(
        select(Website.id, Website.name, func.count(Change.id))
        .outerjoin(Change, Change.website_id == Website.id)
        .group_by(Website.id, Website.name)
        .order_by(Website.name)
    )
    websites = [
        {"website_id": str(website_id), "website": name, "changes": count}
        for website_id, name, count in rows
    ]
    return {
        "mode": "read_only",
        "total_changes": sum(int(item["changes"]) for item in websites),
        "websites": websites,
    }


def reset_change_history(
    db: Session, *, website_id: UUID | None = None
) -> ChangeHistoryReset:
    active_query = select(CrawlJob.id).where(CrawlJob.status.in_(ACTIVE_CRAWL_STATUSES))
    if website_id is not None:
        active_query = active_query.where(CrawlJob.website_id == website_id)
    if db.scalar(active_query.limit(1)):
        raise RuntimeError(
            "Wijzigingshistorie kan niet worden gereset terwijl een betrokken crawl actief, "
            "gepauzeerd of in de wachtrij staat."
        )
    statement = delete(Change)
    if website_id is not None:
        statement = statement.where(Change.website_id == website_id)
    result = db.execute(statement)
    db.commit()
    return ChangeHistoryReset(
        deleted=int(result.rowcount or 0),
        website_id=str(website_id) if website_id else None,
    )

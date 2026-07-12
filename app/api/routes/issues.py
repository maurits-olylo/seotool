import json
from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.crawl import UrlLink, UrlSnapshot
from app.models.discovery import Url
from app.models.integrations import GoogleAnalyticsMetric, SearchConsoleMetric
from app.models.issues import Change, Issue, IssueComment, IssueOccurrence
from app.schemas.issues import (
    ChangeDetailRead,
    ChangeRead,
    CommentCreate,
    CommentRead,
    IssueDetailRead,
    IssueRead,
    IssueUpdate,
)

router = APIRouter(tags=["issues"])


@router.get("/websites/{website_id}/changes", response_model=list[ChangeRead])
def list_changes(
    website_id: UUID,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Change]:
    query = (
        select(Change)
        .where(Change.website_id == website_id)
        .order_by(Change.detected_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(query))


@router.get("/changes/{change_id}", response_model=ChangeDetailRead)
def get_change(change_id: UUID, db: Session = Depends(get_db)) -> dict[str, object]:
    change = db.get(Change, change_id)
    if not change:
        raise HTTPException(status_code=404, detail="Change not found")
    previous = (
        db.get(UrlSnapshot, change.previous_snapshot_id) if change.previous_snapshot_id else None
    )
    current = db.get(UrlSnapshot, change.current_snapshot_id)
    details: dict[str, object] = {
        "old_display": change.old_value,
        "new_display": change.new_value,
    }
    if change.field_name == "links_hash" and current:
        old_links = _snapshot_links(db, previous, change.url_id)
        new_links = _snapshot_links(db, current, change.url_id)
        added = sorted(new_links - old_links)
        removed = sorted(old_links - new_links)
        details = {
            "summary": f"{len(added)} interne links toegevoegd, {len(removed)} verwijderd",
            "added_links": [_link_detail(item) for item in added],
            "removed_links": [_link_detail(item) for item in removed],
            "old_display": _link_display(removed, "Geen verwijderde links"),
            "new_display": _link_display(added, "Geen toegevoegde links"),
        }
    elif change.field_name == "schema_hash" and current:
        old_data = previous.schema_data if previous else []
        new_data = current.schema_data or []
        old_types = set(previous.schema_types or []) if previous else set()
        new_types = set(current.schema_types or [])
        details = {
            "summary": (
                f"Types toegevoegd: {', '.join(sorted(new_types - old_types)) or 'geen'}; "
                f"verwijderd: {', '.join(sorted(old_types - new_types)) or 'geen'}"
            ),
            "old_display": _truncate(json.dumps(old_data, indent=2, ensure_ascii=False)),
            "new_display": _truncate(json.dumps(new_data, indent=2, ensure_ascii=False)),
        }
    elif change.field_name == "main_content_hash" and current:
        details = {
            "summary": "De zichtbare hoofdcontent van de pagina is gewijzigd.",
            "old_display": _truncate(previous.main_content if previous else None),
            "new_display": _truncate(current.main_content),
        }
    return {**ChangeRead.model_validate(change).model_dump(), "details": details}


def _snapshot_links(
    db: Session, snapshot: UrlSnapshot | None, url_id: UUID
) -> set[tuple[str, str, bool]]:
    if not snapshot:
        return set()
    return {
        (target, anchor or "", nofollow)
        for target, anchor, nofollow in db.execute(
            select(UrlLink.target_url, UrlLink.anchor_text, UrlLink.is_nofollow).where(
                UrlLink.crawl_run_id == snapshot.crawl_run_id,
                UrlLink.source_url_id == url_id,
                UrlLink.is_internal.is_(True),
            )
        )
    }


def _link_detail(item: tuple[str, str, bool]) -> dict[str, object]:
    return {"url": item[0], "anchor": item[1], "nofollow": item[2]}


def _link_display(items: list[tuple[str, str, bool]], empty: str) -> str:
    if not items:
        return empty
    return "\n".join(
        f"{url}{f' — {anchor}' if anchor else ''}{' [nofollow]' if nofollow else ''}"
        for url, anchor, nofollow in items
    )


def _truncate(value: str | None, limit: int = 8000) -> str:
    if not value:
        return "Geen inhoud"
    return value if len(value) <= limit else f"{value[:limit]}\n… (ingekort)"


@router.get("/websites/{website_id}/issues", response_model=list[IssueRead])
def list_issues(
    website_id: UUID,
    issue_status: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    query = (
        select(Issue).where(Issue.website_id == website_id).order_by(Issue.last_detected_at.desc())
    )
    if issue_status:
        query = query.where(Issue.status == issue_status)
    issues = list(db.scalars(query))
    impacts = _organic_impacts(db, website_id)
    return [
        {
            **IssueRead.model_validate(issue).model_dump(),
            "organic_impact": impacts.get(issue.url_id),
        }
        for issue in issues
    ]


@router.get("/issues/{issue_id}", response_model=IssueDetailRead)
def get_issue(issue_id: UUID, db: Session = Depends(get_db)) -> dict[str, object]:
    issue = db.get(Issue, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    occurrence = db.scalar(
        select(IssueOccurrence)
        .where(IssueOccurrence.issue_id == issue.id)
        .order_by(desc(IssueOccurrence.detected_at))
        .limit(1)
    )
    source_urls: list[str] = []
    if issue.issue_type == "internally_linked_404" and occurrence and issue.url_id:
        source_urls = list(
            db.scalars(
                select(Url.normalized_url)
                .join(UrlLink, UrlLink.source_url_id == Url.id)
                .where(
                    UrlLink.crawl_run_id == occurrence.crawl_run_id,
                    UrlLink.target_url_id == issue.url_id,
                    UrlLink.is_internal.is_(True),
                )
                .distinct()
                .order_by(Url.normalized_url)
                .limit(100)
            )
        )
    return {
        **IssueRead.model_validate(issue).model_dump(),
        "organic_impact": _organic_impacts(db, issue.website_id).get(issue.url_id),
        "evidence": occurrence.evidence if occurrence else {},
        "source_urls": source_urls,
    }


def _organic_impacts(db: Session, website_id: UUID) -> dict[UUID, dict[str, object]]:
    since = date.today() - timedelta(days=28)
    rows = db.execute(
        select(
            SearchConsoleMetric.url_id,
            func.sum(SearchConsoleMetric.clicks),
            func.sum(SearchConsoleMetric.impressions),
            func.avg(SearchConsoleMetric.position),
        )
        .where(
            SearchConsoleMetric.website_id == website_id,
            SearchConsoleMetric.date >= since,
            SearchConsoleMetric.url_id.is_not(None),
        )
        .group_by(SearchConsoleMetric.url_id)
    )
    result: dict[UUID, dict[str, object]] = {}
    for url_id, clicks, impressions, position in rows:
        click_count = round(float(clicks or 0), 1)
        impression_count = int(impressions or 0)
        level = (
            "high"
            if click_count >= 50 or impression_count >= 5000
            else ("medium" if click_count >= 10 or impression_count >= 1000 else "low")
        )
        result[url_id] = {
            "period_days": 28,
            "clicks": click_count,
            "impressions": impression_count,
            "average_position": round(float(position or 0), 1),
            "level": level,
            "basis": "GSC-klikken en vertoningen",
        }
    analytics_rows = db.execute(
        select(
            GoogleAnalyticsMetric.url_id,
            func.sum(GoogleAnalyticsMetric.sessions),
            func.sum(GoogleAnalyticsMetric.active_users),
            func.sum(GoogleAnalyticsMetric.key_events),
        )
        .where(
            GoogleAnalyticsMetric.website_id == website_id,
            GoogleAnalyticsMetric.date >= since,
            GoogleAnalyticsMetric.url_id.is_not(None),
        )
        .group_by(GoogleAnalyticsMetric.url_id)
    )
    for url_id, sessions, active_users, key_events in analytics_rows:
        impact = result.setdefault(url_id, {"period_days": 28, "level": "unknown"})
        session_count = int(sessions or 0)
        event_count = round(float(key_events or 0), 1)
        ga_level = (
            "high"
            if event_count >= 5 or session_count >= 500
            else ("medium" if event_count >= 1 or session_count >= 100 else "low")
        )
        levels = {"unknown": 0, "low": 1, "medium": 2, "high": 3}
        if levels[ga_level] > levels[str(impact["level"])]:
            impact["level"] = ga_level
        impact.update(
            {
                "sessions": session_count,
                "active_users": int(active_users or 0),
                "key_events": event_count,
                "basis": "GSC-zoekbereik en GA4-landingspaginaverkeer",
            }
        )
    return result


@router.patch("/issues/{issue_id}", response_model=IssueRead)
def update_issue(issue_id: UUID, payload: IssueUpdate, db: Session = Depends(get_db)) -> Issue:
    issue = db.get(Issue, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(issue, key, value)
    db.commit()
    db.refresh(issue)
    return issue


@router.post("/issues/{issue_id}/comments", response_model=CommentRead, status_code=201)
def add_comment(
    issue_id: UUID, payload: CommentCreate, db: Session = Depends(get_db)
) -> IssueComment:
    if not db.get(Issue, issue_id):
        raise HTTPException(status_code=404, detail="Issue not found")
    comment = IssueComment(issue_id=issue_id, **payload.model_dump())
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment

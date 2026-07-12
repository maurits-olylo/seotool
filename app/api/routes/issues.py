from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.crawl import UrlLink
from app.models.discovery import Url
from app.models.integrations import SearchConsoleMetric
from app.models.issues import Change, Issue, IssueComment, IssueOccurrence
from app.schemas.issues import (
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
    db: Session = Depends(get_db),
) -> list[Change]:
    query = (
        select(Change)
        .where(Change.website_id == website_id)
        .order_by(Change.detected_at.desc())
        .limit(limit)
    )
    return list(db.scalars(query))


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
        }
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

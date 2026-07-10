from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.issues import Change, Issue, IssueComment
from app.schemas.issues import (
    ChangeRead,
    CommentCreate,
    CommentRead,
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
) -> list[Issue]:
    query = (
        select(Issue).where(Issue.website_id == website_id).order_by(Issue.last_detected_at.desc())
    )
    if issue_status:
        query = query.where(Issue.status == issue_status)
    return list(db.scalars(query))


@router.get("/issues/{issue_id}", response_model=IssueRead)
def get_issue(issue_id: UUID, db: Session = Depends(get_db)) -> Issue:
    issue = db.get(Issue, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    return issue


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

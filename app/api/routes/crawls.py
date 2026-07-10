from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import Url
from app.schemas.crawl import CrawlRunRead, UrlSnapshotRead

router = APIRouter(tags=["crawls"])


@router.get("/websites/{website_id}/crawl-runs", response_model=list[CrawlRunRead])
def list_crawl_runs(
    website_id: UUID, limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)
) -> list[CrawlRun]:
    query = (
        select(CrawlRun)
        .where(CrawlRun.website_id == website_id)
        .order_by(CrawlRun.started_at.desc())
        .limit(limit)
    )
    return list(db.scalars(query))


@router.get("/urls/{url_id}/snapshots", response_model=list[UrlSnapshotRead])
def list_snapshots(
    url_id: UUID, limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)
) -> list[UrlSnapshot]:
    if not db.get(Url, url_id):
        raise HTTPException(status_code=404, detail="URL not found")
    query = (
        select(UrlSnapshot)
        .where(UrlSnapshot.url_id == url_id)
        .order_by(UrlSnapshot.checked_at.desc())
        .limit(limit)
    )
    return list(db.scalars(query))


@router.get("/snapshots/{snapshot_id}", response_model=UrlSnapshotRead)
def get_snapshot(snapshot_id: UUID, db: Session = Depends(get_db)) -> UrlSnapshot:
    snapshot = db.get(UrlSnapshot, snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snapshot

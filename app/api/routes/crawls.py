from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import Url
from app.schemas.crawl import CrawlRunRead, UrlSnapshotRead
from app.services.authorization import require_website_access

router = APIRouter(tags=["crawls"])


@router.get("/websites/{website_id}/crawl-runs", response_model=list[CrawlRunRead])
def list_crawl_runs(
    website_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> list[CrawlRun]:
    require_website_access(db, principal, website_id)
    query = (
        select(CrawlRun)
        .where(CrawlRun.website_id == website_id)
        .order_by(CrawlRun.started_at.desc())
        .limit(limit)
    )
    return list(db.scalars(query))


@router.get("/urls/{url_id}/snapshots", response_model=list[UrlSnapshotRead])
def list_snapshots(
    url_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> list[UrlSnapshot]:
    url = db.get(Url, url_id)
    if not url:
        raise HTTPException(status_code=404, detail="URL not found")
    require_website_access(db, principal, url.website_id)
    query = (
        select(UrlSnapshot)
        .where(UrlSnapshot.url_id == url_id)
        .order_by(UrlSnapshot.checked_at.desc())
        .limit(limit)
    )
    return list(db.scalars(query))


@router.get("/snapshots/{snapshot_id}", response_model=UrlSnapshotRead)
def get_snapshot(
    snapshot_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> UrlSnapshot:
    snapshot = db.get(UrlSnapshot, snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    url = db.get(Url, snapshot.url_id)
    if not url:
        raise HTTPException(status_code=404, detail="URL not found")
    require_website_access(db, principal, url.website_id)
    return snapshot

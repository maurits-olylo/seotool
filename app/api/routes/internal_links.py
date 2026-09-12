from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.models.crawl import CrawlRun
from app.models.discovery import Url
from app.services.authorization import require_website_access
from app.services.internal_links import ranking, referring_pages

router = APIRouter(tags=["internal links"])


@router.get("/websites/{website_id}/internal-links")
def internal_link_ranking(
    website_id: UUID,
    q: str = Query(default="", max_length=200),
    view: Literal[
        "all", "pages", "attention", "low", "lost", "errors", "repeated", "technical"
    ] = "all",
    order: Literal["links_desc", "links_asc", "url", "priority"] = "links_desc",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, Any]:
    require_website_access(db, principal, website_id)
    result = ranking(db, website_id)
    items = [item for item in result["items"] if q.casefold() in item["url"].casefold()]
    if view == "pages":
        items = [item for item in items if "technical" not in item["signals"]]
    elif view != "all":
        items = [item for item in items if view in item["signals"]]
    if order == "priority":
        items.sort(
            key=lambda item: (
                0 if "errors" in item["signals"] else 1 if "lost" in item["signals"] else 2,
                -item["incoming_pages"] if "errors" in item["signals"] else (item["change"] or 0),
                item["incoming_pages"],
                item["url"],
            )
        )
    elif order == "links_asc":
        items.sort(key=lambda item: (item["incoming_pages"], item["url"]))
    elif order == "url":
        items.sort(key=lambda item: item["url"])
    return {**result, "total": len(items), "items": items[offset : offset + limit]}


@router.get("/websites/{website_id}/internal-links/{url_id}/sources")
def internal_link_sources(
    website_id: UUID,
    url_id: UUID,
    crawl_run_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, Any]:
    require_website_access(db, principal, website_id)
    run = db.get(CrawlRun, crawl_run_id)
    target = db.get(Url, url_id)
    if (
        not run
        or run.website_id != website_id
        or run.status != "succeeded"
        or run.crawl_type != "full_site_crawl"
        or not run.finished_at
        or not target
        or target.website_id != website_id
    ):
        raise HTTPException(status_code=404, detail="URL of volledige crawl niet beschikbaar")
    return referring_pages(db, run, url_id, offset, limit)

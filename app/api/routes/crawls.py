from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.models.crawl import CrawlRun, UrlLink, UrlSnapshot
from app.models.discovery import Url, UrlSource
from app.schemas.crawl import CrawlFailureRead, CrawlRunRead, UrlSnapshotRead
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


@router.get("/crawl-runs/{crawl_run_id}/failures", response_model=list[CrawlFailureRead])
def list_crawl_failures(
    crawl_run_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> list[CrawlFailureRead]:
    run = db.get(CrawlRun, crawl_run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Crawl run not found")
    require_website_access(db, principal, run.website_id)
    rows = list(
        db.execute(
            select(UrlSnapshot, Url)
            .join(Url, Url.id == UrlSnapshot.url_id)
            .where(
                UrlSnapshot.crawl_run_id == crawl_run_id,
                UrlSnapshot.error_message.is_not(None),
            )
            .order_by(UrlSnapshot.requested_url)
        )
    )
    failures: list[CrawlFailureRead] = []
    for snapshot, url in rows:
        source_types = sorted(
            set(
                db.scalars(
                    select(UrlSource.source_type).where(
                        UrlSource.url_id == url.id,
                        UrlSource.last_seen_at >= run.started_at,
                    )
                )
            )
        )
        incoming_links = int(
            db.scalar(
                select(func.count(UrlLink.id)).where(
                    UrlLink.crawl_run_id == crawl_run_id,
                    UrlLink.target_url_id == url.id,
                    UrlLink.is_internal.is_(True),
                )
            )
            or 0
        )
        assessment, explanation, action = _failure_guidance(
            snapshot.error_message or "",
            source_types=source_types,
            incoming_links=incoming_links,
        )
        failures.append(
            CrawlFailureRead(
                snapshot_id=snapshot.id,
                url_id=url.id,
                requested_url=snapshot.requested_url,
                error_message=snapshot.error_message or "Onbekende crawlfout",
                source_types=source_types,
                incoming_internal_links=incoming_links,
                assessment=assessment,
                explanation=explanation,
                recommended_action=action,
            )
        )
    return failures


def _failure_guidance(
    error_message: str,
    *,
    source_types: list[str],
    incoming_links: int,
) -> tuple[str, str, str]:
    current_reference = incoming_links > 0 or bool({"sitemap", "internal_link"} & set(source_types))
    normalized_error = error_message.lower()
    if not current_reference:
        return (
            "informational",
            "De URL is alleen historisch bekend en is in deze crawl niet opnieuw gevonden.",
            "Geen directe actie nodig. Controleer alleen of de URL bewust is verwijderd.",
        )
    if "redirect loop" in normalized_error:
        return (
            "action_required",
            "Zoekmachines en bezoekers bereiken door de redirectlus geen eindpagina.",
            "Herstel de redirectregels en vervang interne links direct door de juiste eind-URL.",
        )
    if "hostname could not be resolved" in normalized_error:
        return (
            "action_required",
            "De hostname bestaat niet of kan niet via DNS worden bereikt.",
            "Corrigeer of verwijder de interne link of sitemap-URL en gebruik de "
            "bereikbare HTTPS-URL.",
        )
    if "timed out" in normalized_error or "timeout" in normalized_error:
        return (
            "retry",
            "De URL reageerde niet binnen de ingestelde tijd; dit kan tijdelijk zijn.",
            "Probeer de URL opnieuw. Onderzoek serverbelasting wanneer de fout terugkomt.",
        )
    return (
        "review",
        "De crawler kon de URL niet volledig controleren.",
        "Controleer de foutmelding en probeer de URL opnieuw voordat je content wijzigt.",
    )


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

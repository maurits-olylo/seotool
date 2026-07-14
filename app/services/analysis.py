import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.crawl import UrlLink, UrlSnapshot
from app.models.discovery import Url
from app.models.issues import Change
from app.services.change_detection import DetectedChange, compare_snapshots
from app.services.issue_engine import reconcile_issues
from app.services.job_listings import update_job_listing
from app.services.job_posting import inspect_job_posting
from app.services.technical_checks import SNAPSHOT_ISSUE_TYPES, inspect_snapshot


def analyze_snapshot(db: Session, snapshot: UrlSnapshot) -> None:
    url = db.get(Url, snapshot.url_id)
    if url is None:
        raise ValueError("Snapshot URL does not exist")
    previous = db.scalar(
        select(UrlSnapshot)
        .where(UrlSnapshot.url_id == snapshot.url_id, UrlSnapshot.id != snapshot.id)
        .order_by(UrlSnapshot.checked_at.desc())
        .limit(1)
    )
    detected_changes = compare_snapshots(previous, snapshot)
    if previous:
        old_links = _internal_links(db, previous)
        new_links = _internal_links(db, snapshot)
        if old_links != new_links:
            detected_changes.append(
                DetectedChange(
                    "internal_links_changed",
                    "internal_links",
                    json.dumps(old_links, ensure_ascii=False),
                    json.dumps(new_links, ensure_ascii=False),
                )
            )
    for detected in detected_changes:
        db.add(
            Change(
                website_id=url.website_id,
                url_id=url.id,
                previous_snapshot_id=previous.id if previous else None,
                current_snapshot_id=snapshot.id,
                change_type=detected.change_type,
                field_name=detected.field_name,
                old_value=detected.old_value,
                new_value=detected.new_value,
            )
        )
    signals = inspect_snapshot(snapshot)
    inbound_internal_links = (
        db.scalar(
            select(func.count(UrlLink.id)).where(
                UrlLink.crawl_run_id == snapshot.crawl_run_id,
                UrlLink.target_url_id == url.id,
                UrlLink.is_internal.is_(True),
            )
        )
        or 0
    )
    application_url = db.scalar(
        select(UrlLink.target_url).where(
            UrlLink.crawl_run_id == snapshot.crawl_run_id,
            UrlLink.source_url_id == url.id,
            UrlLink.is_internal.is_(True),
            UrlLink.anchor_text.ilike("%solliciteer%")
            | UrlLink.anchor_text.ilike("%reageer%")
            | UrlLink.anchor_text.ilike("%aanmelden%"),
        )
    )
    update_job_listing(
        db,
        url=url,
        snapshot=snapshot,
        inbound_internal_links=inbound_internal_links,
        application_url=application_url,
    )
    if not snapshot.redirect_chain:
        signals.extend(
            inspect_job_posting(
                snapshot.schema_data or [],
                status_code=snapshot.status_code,
                page_url=url.normalized_url,
                main_content=snapshot.main_content,
                has_application_cta=application_url is not None,
                inbound_internal_links=inbound_internal_links,
                was_job_posting=bool(previous and "JobPosting" in (previous.schema_types or [])),
            )
        )
    reconcile_issues(
        db,
        website_id=url.website_id,
        url_id=url.id,
        crawl_run_id=snapshot.crawl_run_id,
        snapshot_id=snapshot.id,
        signals=signals,
        checked_issue_types=SNAPSHOT_ISSUE_TYPES,
    )


def _internal_links(db: Session, snapshot: UrlSnapshot) -> list[tuple[str, str, bool]]:
    return sorted(
        {
            (target, anchor or "", nofollow)
            for target, anchor, nofollow in db.execute(
                select(UrlLink.target_url, UrlLink.anchor_text, UrlLink.is_nofollow).where(
                    UrlLink.crawl_run_id == snapshot.crawl_run_id,
                    UrlLink.source_url_id == snapshot.url_id,
                    UrlLink.is_internal.is_(True),
                )
            )
        }
    )

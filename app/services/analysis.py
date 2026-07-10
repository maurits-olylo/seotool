from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crawl import UrlSnapshot
from app.models.discovery import Url
from app.models.issues import Change
from app.services.change_detection import compare_snapshots
from app.services.issue_engine import reconcile_issues
from app.services.job_posting import inspect_job_posting
from app.services.technical_checks import inspect_snapshot


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
    for detected in compare_snapshots(previous, snapshot):
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
    signals.extend(
        inspect_job_posting(snapshot.schema_data or [], status_code=snapshot.status_code)
    )
    reconcile_issues(
        db,
        website_id=url.website_id,
        url_id=url.id,
        crawl_run_id=snapshot.crawl_run_id,
        snapshot_id=snapshot.id,
        signals=signals,
    )

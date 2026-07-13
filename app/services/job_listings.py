from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crawl import UrlSnapshot
from app.models.discovery import Url
from app.models.jobs import JobListing
from app.services.job_posting import recognize_job_listing


def update_job_listing(
    db: Session,
    *,
    url: Url,
    snapshot: UrlSnapshot,
    inbound_internal_links: int,
    application_url: str | None,
    today: date | None = None,
) -> JobListing | None:
    """Create or refresh the current vacancy state from a crawl snapshot."""
    recognized = recognize_job_listing(
        snapshot.schema_data or [],
        page_url=url.normalized_url,
        title=snapshot.title,
        headings=snapshot.headings,
        main_content=snapshot.main_content,
        status_code=snapshot.status_code,
        redirect_chain=snapshot.redirect_chain,
        application_url=application_url,
        today=today,
    )
    existing = db.scalar(
        select(JobListing).where(
            JobListing.website_id == url.website_id,
            JobListing.url_id == url.id,
        )
    )
    if recognized is None:
        return existing
    now = datetime.now(UTC)
    if existing is None:
        existing = JobListing(
            website_id=url.website_id,
            url_id=url.id,
            first_detected_at=now,
        )
        db.add(existing)
    existing.latest_snapshot_id = snapshot.id
    existing.detection_sources = recognized.detection_sources
    existing.title = recognized.title
    existing.employer = recognized.employer
    existing.locations = recognized.locations
    existing.date_posted = recognized.date_posted
    existing.valid_through = recognized.valid_through
    existing.salary_data = recognized.salary_data
    existing.hours = recognized.hours
    existing.employment_types = recognized.employment_types
    existing.external_identifier = recognized.external_identifier
    existing.application_url = recognized.application_url
    existing.job_posting_data = recognized.job_posting_data
    existing.lifecycle_status = existing.manual_status or recognized.lifecycle_status
    existing.current_status_code = snapshot.status_code
    existing.is_indexable = snapshot.is_indexable
    existing.inbound_internal_links = inbound_internal_links
    existing.last_detected_at = now
    url.page_type = "job"
    return existing

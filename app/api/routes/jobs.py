from collections import defaultdict
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.models.discovery import Url
from app.models.issues import Issue
from app.models.jobs import JobListing
from app.services.authorization import require_website_access
from app.services.job_posting import ACTIVE_JOB_ISSUE_STATUSES, JOB_ISSUE_TYPES

router = APIRouter(tags=["job listings"])

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@router.get("/websites/{website_id}/job-listings")
def list_job_listings(
    website_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    """Return current vacancy facts and the issues that affect Google for Jobs."""
    require_website_access(db, principal, website_id)
    listings = list(
        db.execute(
            select(JobListing, Url.normalized_url)
            .join(Url, Url.id == JobListing.url_id)
            .where(JobListing.website_id == website_id)
            .order_by(JobListing.valid_through.asc().nullslast(), Url.normalized_url)
        )
    )
    url_ids = [listing.url_id for listing, _ in listings]
    issues_by_url: dict[UUID, list[Issue]] = defaultdict(list)
    if url_ids:
        for issue in db.scalars(
            select(Issue).where(
                Issue.website_id == website_id,
                Issue.url_id.in_(url_ids),
                Issue.issue_type.in_(JOB_ISSUE_TYPES),
                Issue.status.in_(ACTIVE_JOB_ISSUE_STATUSES),
            )
        ):
            if issue.url_id:
                issues_by_url[issue.url_id].append(issue)

    rows = [
        _listing_payload(listing, url, issues_by_url.get(listing.url_id, []))
        for listing, url in listings
    ]
    active_issues = [issue for row in rows for issue in row["issues"]]
    return {
        "summary": {
            "total": len(rows),
            "active": sum(row["lifecycle_status"] == "active" for row in rows),
            "expiring_soon": sum(row["lifecycle_status"] == "expiring_soon" for row in rows),
            "expired": sum(row["lifecycle_status"] == "expired" for row in rows),
            "removed": sum(row["lifecycle_status"] == "removed" for row in rows),
            "needs_attention": sum(bool(row["issues"]) for row in rows),
            "technical_errors": sum(row["validation_status"] == "error" for row in rows),
            "missing_schema": sum(not row["has_job_posting_schema"] for row in rows),
            "new_issues": sum(issue["status"] == "new" for issue in active_issues),
        },
        "job_listings": rows,
    }


def _listing_payload(listing: JobListing, url: str, issues: list[Issue]) -> dict[str, object]:
    ordered_issues = sorted(issues, key=lambda issue: SEVERITY_ORDER.get(issue.severity, 99))
    has_schema = "job_posting_schema" in (listing.detection_sources or [])
    if any(issue.severity in {"critical", "high"} for issue in ordered_issues):
        validation_status = "error"
    elif ordered_issues:
        validation_status = "warning"
    elif has_schema:
        validation_status = "valid"
    else:
        validation_status = "not_available"
    return {
        "id": str(listing.id),
        "url_id": str(listing.url_id),
        "url": url,
        "title": listing.title,
        "employer": listing.employer,
        "locations": listing.locations or [],
        "date_posted": listing.date_posted,
        "valid_through": listing.valid_through,
        "employment_types": listing.employment_types or [],
        "application_url": listing.application_url,
        "lifecycle_status": listing.lifecycle_status,
        "current_status_code": listing.current_status_code,
        "is_indexable": listing.is_indexable,
        "inbound_internal_links": listing.inbound_internal_links,
        "detection_sources": listing.detection_sources or [],
        "has_job_posting_schema": has_schema,
        "validation_status": validation_status,
        "issues": [
            {
                "id": str(issue.id),
                "title": issue.title,
                "severity": issue.severity,
                "status": issue.status,
                "recommended_action": issue.recommended_action,
            }
            for issue in ordered_issues
        ],
    }

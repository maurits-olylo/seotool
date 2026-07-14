import math
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crawl import UrlSnapshot
from app.models.discovery import Url
from app.models.issues import Issue
from app.services.issue_engine import reconcile_issues
from app.services.technical_checks import IssueSignal
from app.services.url_filtering import is_probable_html_page

BREADCRUMB_ISSUE_TYPES = {"missing_breadcrumb_schema"}
MINIMUM_BREADCRUMB_EXAMPLES = 3
MINIMUM_BREADCRUMB_COVERAGE = 0.5


def analyze_breadcrumb_consistency(
    db: Session, *, website_id: object, crawl_run_id: object
) -> list[Issue]:
    """Report missing BreadcrumbList only when the site demonstrably uses it."""
    rows = list(
        db.execute(
            select(Url, UrlSnapshot)
            .join(UrlSnapshot, UrlSnapshot.url_id == Url.id)
            .where(
                Url.website_id == website_id,
                UrlSnapshot.crawl_run_id == crawl_run_id,
            )
            .order_by(Url.normalized_url)
        )
    )
    eligible_indices = [
        index for index, (url, snapshot) in enumerate(rows) if _is_deep_content_page(url, snapshot)
    ]
    with_breadcrumb = [
        index
        for index in eligible_indices
        if "BreadcrumbList" in (rows[index][1].schema_types or [])
    ]
    minimum_expected = max(
        MINIMUM_BREADCRUMB_EXAMPLES,
        math.ceil(len(eligible_indices) * MINIMUM_BREADCRUMB_COVERAGE),
    )
    site_uses_breadcrumbs = len(with_breadcrumb) >= minimum_expected
    eligible_set = set(eligible_indices)
    breadcrumb_set = set(with_breadcrumb)
    touched: list[Issue] = []

    for index, (url, snapshot) in enumerate(rows):
        signals: list[IssueSignal] = []
        if site_uses_breadcrumbs and index in eligible_set and index not in breadcrumb_set:
            signals.append(
                IssueSignal(
                    issue_type="missing_breadcrumb_schema",
                    category="structured_data",
                    severity="low",
                    confidence="high",
                    title="Breadcrumb structured data ontbreekt",
                    description=(
                        "Vergelijkbare diepe pagina's gebruiken BreadcrumbList, maar deze "
                        "indexeerbare pagina niet."
                    ),
                    recommended_action=(
                        "Voeg een BreadcrumbList toe die overeenkomt met de zichtbare "
                        "broodkruimelnavigatie."
                    ),
                    evidence={
                        "crawl_depth": url.crawl_depth,
                        "eligible_pages": len(eligible_indices),
                        "pages_with_breadcrumb_schema": len(with_breadcrumb),
                        "site_coverage_percent": round(
                            len(with_breadcrumb) / len(eligible_indices) * 100, 1
                        ),
                    },
                )
            )
        touched.extend(
            reconcile_issues(
                db,
                website_id=website_id,
                url_id=url.id,
                crawl_run_id=crawl_run_id,
                snapshot_id=snapshot.id,
                signals=signals,
                checked_issue_types=BREADCRUMB_ISSUE_TYPES,
            )
        )
    db.commit()
    return touched


def _is_deep_content_page(url: Url, snapshot: UrlSnapshot) -> bool:
    parsed = urlsplit(url.normalized_url)
    return bool(
        url.is_active
        and url.current_status_code == 200
        and url.is_indexable is True
        and (url.crawl_depth or 0) >= 2
        and not parsed.query
        and is_probable_html_page(url.normalized_url)
        and snapshot.status_code == 200
        and snapshot.is_indexable is True
        and not snapshot.redirect_chain
    )

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crawl import UrlSnapshot
from app.models.discovery import Url
from app.models.issues import Issue
from app.services.content_similarity import near_duplicate_groups
from app.services.issue_engine import reconcile_issues
from app.services.job_posting import job_posting_identifier
from app.services.technical_checks import IssueSignal

IDENTIFIER_RISK_ISSUE_TYPES = {"job_posting_identifier_collision_risk"}
MEDIUM_RISK_GROUP_SIZE = 5


def analyze_job_identifier_risk(
    db: Session, *, website_id: object, crawl_run_id: object
) -> list[Issue]:
    """Signal missing identifiers only when similar vacancies can be confused."""
    all_rows = list(
        db.execute(
            select(Url, UrlSnapshot)
            .join(UrlSnapshot, UrlSnapshot.url_id == Url.id)
            .where(
                Url.website_id == website_id,
                UrlSnapshot.crawl_run_id == crawl_run_id,
                UrlSnapshot.status_code == 200,
                UrlSnapshot.is_indexable.is_(True),
            )
            .order_by(Url.normalized_url)
        )
    )
    rows = [
        row
        for row in all_rows
        if "JobPosting" in (row[1].schema_types or [])
        and job_posting_identifier(row[1].schema_data or []) is None
    ]
    signals_by_index: dict[int, list[IssueSignal]] = defaultdict(list)
    for group, scores in near_duplicate_groups(rows, excluded_indices=set()):
        urls = [rows[index][0].normalized_url for index in group]
        severity = "medium" if len(group) >= MEDIUM_RISK_GROUP_SIZE else "low"
        confidence = "high" if len(group) >= MEDIUM_RISK_GROUP_SIZE else "medium"
        minimum_overlap = round(min(scores) * 100, 1)
        for index in group:
            related_urls = [url for url in urls if url != rows[index][0].normalized_url]
            signals_by_index[index].append(
                IssueSignal(
                    issue_type="job_posting_identifier_collision_risk",
                    category="structured_data",
                    severity=severity,
                    confidence=confidence,
                    title="Vergelijkbare vacatures missen een unieke identifier",
                    description=(
                        f"Deze vacature lijkt sterk op {len(related_urls)} andere vacature(s); "
                        "geen van deze pagina's bevat een stabiele identifier. Daardoor zijn "
                        "afzonderlijke vacatures minder eenduidig te herkennen."
                    ),
                    recommended_action=(
                        "Voeg per vacature een unieke, blijvende JobPosting-identifier toe die "
                        "ook bij tekst- of URL-wijzigingen gelijk blijft."
                    ),
                    evidence={
                        "missing_field": "identifier",
                        "group_size": len(group),
                        "related_urls": related_urls,
                        "minimum_content_overlap_percent": minimum_overlap,
                        "source": "cross_vacancy_similarity",
                    },
                )
            )

    touched: list[Issue] = []
    for index, (url, snapshot) in enumerate(rows):
        touched.extend(
            reconcile_issues(
                db,
                website_id=website_id,
                url_id=url.id,
                crawl_run_id=crawl_run_id,
                snapshot_id=snapshot.id,
                signals=signals_by_index.get(index, []),
                checked_issue_types=IDENTIFIER_RISK_ISSUE_TYPES,
            )
        )
    return touched

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
    clusters: list[dict[str, object]] = []
    affected_urls: set[str] = set()
    largest_group = 0
    for group, scores in near_duplicate_groups(rows, excluded_indices=set()):
        urls = [rows[index][0].normalized_url for index in group]
        affected_urls.update(urls)
        largest_group = max(largest_group, len(group))
        clusters.append(
            {
                "group_size": len(group),
                "urls": urls,
                "minimum_content_overlap_percent": round(min(scores) * 100, 1),
            }
        )

    touched: list[Issue] = []
    for url, snapshot in rows:
        reconcile_issues(
            db,
            website_id=website_id,
            url_id=url.id,
            crawl_run_id=crawl_run_id,
            snapshot_id=snapshot.id,
            signals=[],
            checked_issue_types=IDENTIFIER_RISK_ISSUE_TYPES,
        )
    signals: list[IssueSignal] = []
    if clusters:
        vacancy_count = len(affected_urls)
        cluster_count = len(clusters)
        severity = "medium" if largest_group >= MEDIUM_RISK_GROUP_SIZE else "low"
        confidence = "high" if largest_group >= MEDIUM_RISK_GROUP_SIZE else "medium"
        signals.append(
            IssueSignal(
                issue_type="job_posting_identifier_collision_risk",
                category="structured_data",
                severity=severity,
                confidence=confidence,
                title=f"{vacancy_count} vergelijkbare vacatures missen een identifier",
                description=(
                    f"Binnen {cluster_count} inhoudelijk vergelijkbare vacaturecluster(s) missen "
                    f"in totaal {vacancy_count} vacatures een stabiele identifier. Daardoor zijn "
                    "afzonderlijke vacatures minder eenduidig te herkennen."
                ),
                recommended_action=(
                    "Pas het JobPosting-template één keer aan: voeg per vacature een unieke, "
                    "blijvende identifier toe die ook bij tekst- of URL-wijzigingen gelijk "
                    "blijft. Controleer daarna alle onderstaande clusters in één vervolgcrawl."
                ),
                evidence={
                    "missing_field": "identifier",
                    "affected_vacancies": vacancy_count,
                    "cluster_count": cluster_count,
                    "largest_cluster": largest_group,
                    "clusters": clusters,
                    "likely_scope": "gedeeld JobPosting-template",
                    "verification": "iedere vacature in deze clusters heeft een unieke identifier",
                    "source": "cross_vacancy_similarity",
                },
            )
        )
    touched.extend(
        reconcile_issues(
            db,
            website_id=website_id,
            url_id=None,
            crawl_run_id=crawl_run_id,
            snapshot_id=None,
            signals=signals,
            checked_issue_types=IDENTIFIER_RISK_ISSUE_TYPES,
        )
    )
    return touched

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.common import utc_now
from app.models.issues import Issue, IssueOccurrence
from app.services.technical_checks import IssueSignal

REOPENABLE_STATUSES = {"resolved", "verified", "ignored", "accepted_risk"}


def reconcile_issues(
    db: Session,
    *,
    website_id: object,
    url_id: object,
    crawl_run_id: object,
    snapshot_id: object,
    signals: Iterable[IssueSignal],
    checked_issue_types: set[str],
) -> list[Issue]:
    now = utc_now()
    signal_map = {signal.issue_type: signal for signal in signals}
    existing = list(
        db.scalars(select(Issue).where(Issue.website_id == website_id, Issue.url_id == url_id))
    )
    by_type = {issue.issue_type: issue for issue in existing}
    touched: list[Issue] = []
    for issue_type, signal in signal_map.items():
        issue = by_type.get(issue_type)
        if issue is None:
            issue = Issue(
                website_id=website_id,
                url_id=url_id,
                issue_type=signal.issue_type,
                category=signal.category,
                severity=signal.severity,
                confidence=signal.confidence,
                title=signal.title,
                description=signal.description,
                recommended_action=signal.recommended_action,
            )
            db.add(issue)
            db.flush()
        else:
            issue.last_detected_at = now
            issue.severity = signal.severity
            issue.confidence = signal.confidence
            issue.title = signal.title
            issue.description = signal.description
            issue.recommended_action = signal.recommended_action
            if issue.status in REOPENABLE_STATUSES:
                issue.status = "new"
                issue.resolved_at = None
                issue.verified_at = None
        occurrence = db.scalar(
            select(IssueOccurrence).where(
                IssueOccurrence.issue_id == issue.id,
                IssueOccurrence.crawl_run_id == crawl_run_id,
            )
        )
        if occurrence is None:
            db.add(
                IssueOccurrence(
                    issue_id=issue.id,
                    crawl_run_id=crawl_run_id,
                    snapshot_id=snapshot_id,
                    evidence=signal.evidence,
                )
            )
        else:
            occurrence.evidence = signal.evidence
        touched.append(issue)

    for issue in existing:
        if issue.issue_type not in checked_issue_types or issue.issue_type in signal_map:
            continue
        if issue.status == "resolved":
            issue.status = "verified"
            issue.verified_at = now
        elif issue.status not in {"verified", "ignored", "accepted_risk"}:
            issue.status = "resolved"
            issue.resolved_at = now
    return touched


def verify_resolved_issues(db: Session, *, website_id: object, url_id: object) -> int:
    now = utc_now()
    issues = list(
        db.scalars(
            select(Issue).where(
                Issue.website_id == website_id,
                Issue.url_id == url_id,
                Issue.status == "resolved",
            )
        )
    )
    for issue in issues:
        issue.status = "verified"
        issue.verified_at = now
    return len(issues)

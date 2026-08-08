import hashlib
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.issues import Issue, IssueOccurrence

ACTIVE_ISSUE_STATUSES = {
    "new",
    "review",
    "accepted",
    "planned",
    "in_progress",
    "waiting_for_client",
}
MAX_GROUPED_ISSUES = 50
_POSITIONAL_SELECTOR = re.compile(r":nth-(?:child|of-type)\(\d+\)", re.IGNORECASE)


def component_signature(rule_id: str, target: object) -> str | None:
    """Return a stable signature for the same rule on the same shared component."""
    if not isinstance(target, list) or not target:
        return None
    parts = [
        _POSITIONAL_SELECTOR.sub(":nth-child(*)", str(value).strip())[:500]
        for value in target[:3]
        if str(value).strip()
    ]
    if not parts:
        return None
    digest = hashlib.sha256(" > ".join(parts).encode()).hexdigest()[:16]
    return f"axe:{rule_id}:{digest}"


def accessibility_issue_group(db: Session, issue: Issue) -> list[Issue]:
    """Find active issues with the same persisted component signature in one website."""
    if issue.category != "accessibility":
        return [issue]
    signature = _latest_component_signature(db, issue.id)
    if signature is None:
        return [issue]
    candidates = list(
        db.scalars(
            select(Issue)
            .where(
                Issue.website_id == issue.website_id,
                Issue.issue_type == issue.issue_type,
                Issue.category == "accessibility",
                Issue.status.in_(ACTIVE_ISSUE_STATUSES),
            )
            .order_by(Issue.first_detected_at, Issue.id)
            .limit(MAX_GROUPED_ISSUES)
        )
    )
    matching = [
        candidate
        for candidate in candidates
        if _latest_component_signature(db, candidate.id) == signature
    ]
    return [issue, *(candidate for candidate in matching if candidate.id != issue.id)]


def _latest_component_signature(db: Session, issue_id: object) -> str | None:
    evidence = db.scalar(
        select(IssueOccurrence.evidence)
        .where(IssueOccurrence.issue_id == issue_id)
        .order_by(IssueOccurrence.detected_at.desc())
        .limit(1)
    )
    accessibility = evidence.get("accessibility") if isinstance(evidence, dict) else None
    signature = (
        accessibility.get("component_signature")
        if isinstance(accessibility, dict)
        else None
    )
    return signature if isinstance(signature, str) and signature else None

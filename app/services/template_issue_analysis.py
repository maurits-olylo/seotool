import re
from collections import defaultdict
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.discovery import Url
from app.models.issues import Issue, IssueOccurrence
from app.services.issue_engine import reconcile_issues
from app.services.pagination_analysis import PAGINATION_CHILD_ISSUE_TYPES
from app.services.technical_checks import IssueSignal

TEMPLATE_CLUSTER_ISSUE_TYPE = "template_signal_clusters"
CLUSTERABLE_ISSUE_TYPES = {
    "canonical_other_url",
    "deep_page",
    "duplicate_meta_description",
    "duplicate_title",
    "missing_h1",
    "missing_meta_description",
    "multiple_h1",
    "orphan_page",
    "thin_content",
}
ACTIVE_STATUSES = {
    "new",
    "review",
    "accepted",
    "planned",
    "in_progress",
    "waiting_for_client",
}
MINIMUM_CLUSTER_SIZE = {
    "canonical_other_url": 3,
    "deep_page": 10,
    "duplicate_meta_description": 2,
    "duplicate_title": 2,
    "missing_h1": 5,
    "missing_meta_description": 5,
    "multiple_h1": 5,
    "orphan_page": 5,
    "thin_content": 5,
}
HIERARCHICAL_ISSUE_TYPES = {
    "deep_page",
    "missing_h1",
    "missing_meta_description",
    "multiple_h1",
    "orphan_page",
    "thin_content",
}
NUMBER_RE = re.compile(r"\d+")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f-]{27,}$", re.IGNORECASE)


def analyze_template_issue_clusters(
    db: Session, *, website_id: object, crawl_run_id: object
) -> list[Issue]:
    """Group repeated URL-level signals when one template-level review is actionable."""
    issues = list(
        db.scalars(
            select(Issue).where(
                Issue.website_id == website_id,
                Issue.url_id.is_not(None),
                Issue.issue_type.in_(CLUSTERABLE_ISSUE_TYPES),
                Issue.status.in_(ACTIVE_STATUSES),
            )
        )
    )
    issue_ids = {issue.id for issue in issues}
    latest_by_issue: dict[object, IssueOccurrence] = {}
    if issue_ids:
        for occurrence in db.scalars(
            select(IssueOccurrence)
            .where(IssueOccurrence.issue_id.in_(issue_ids))
            .order_by(IssueOccurrence.issue_id, IssueOccurrence.detected_at.desc())
        ):
            latest_by_issue.setdefault(occurrence.issue_id, occurrence)

    url_ids = {issue.url_id for issue in issues if issue.url_id is not None}
    urls_by_id = {
        url.id: url for url in db.scalars(select(Url).where(Url.id.in_(url_ids)))
    }
    pagination_urls = _active_diagnosis_urls(
        db,
        website_id=website_id,
        issue_type="pagination_series_review",
    )
    grouped: dict[tuple[str, str], list[tuple[Issue, Url, dict[str, object]]]] = defaultdict(
        list
    )
    for issue in issues:
        url = urls_by_id.get(issue.url_id)
        if url is None:
            continue
        if (
            issue.issue_type in PAGINATION_CHILD_ISSUE_TYPES
            and url.normalized_url in pagination_urls
        ):
            continue
        occurrence = latest_by_issue.get(issue.id)
        evidence = occurrence.evidence if occurrence else {}
        key = _cluster_key(issue.issue_type, evidence, url.normalized_url)
        if key is None:
            continue
        grouped[(issue.issue_type, key)].append((issue, url, evidence))

    clusters: list[dict[str, object]] = []
    affected_pairs: set[tuple[str, str]] = set()
    covered_issue_ids: set[object] = set()
    for (issue_type, cluster_key), items in sorted(grouped.items()):
        if _append_cluster(
            clusters,
            affected_pairs,
            issue_type=issue_type,
            cluster_key=cluster_key,
            items=items,
        ):
            covered_issue_ids.update(issue.id for issue, _url, _evidence in items)

    parent_groups: dict[
        tuple[str, str], list[tuple[Issue, Url, dict[str, object]]]
    ] = defaultdict(list)
    for items in grouped.values():
        for item in items:
            issue, url, evidence = item
            if issue.id in covered_issue_ids or issue.issue_type not in HIERARCHICAL_ISSUE_TYPES:
                continue
            parent_key = _parent_cluster_key(
                issue.issue_type, evidence, url.normalized_url
            )
            parent_groups[(issue.issue_type, parent_key)].append(item)
    for (issue_type, cluster_key), items in sorted(parent_groups.items()):
        _append_cluster(
            clusters,
            affected_pairs,
            issue_type=issue_type,
            cluster_key=cluster_key,
            items=items,
        )

    signals: list[IssueSignal] = []
    if clusters:
        signals.append(
            IssueSignal(
                issue_type=TEMPLATE_CLUSTER_ISSUE_TYPE,
                category="onpage",
                severity="medium",
                confidence="high",
                title=(
                    f"{len(affected_pairs)} URL-signalen vormen "
                    f"{len(clusters)} herkenbare templateclusters"
                ),
                description=(
                    "Dezelfde signalen komen terug binnen herkenbare URL-families of gebruiken "
                    "dezelfde metadatawaarde. Ze worden daarom als templatecontrole getoond in "
                    "plaats van als losse taak per URL."
                ),
                recommended_action=(
                    "Beoordeel ieder cluster één keer op template-, component- of contenttype-"
                    "niveau. Pas alleen aantoonbaar onbedoelde patronen centraal aan en controleer "
                    "met een volgende volledige crawl welke URL-signalen verdwijnen."
                ),
                evidence={
                    "affected_signal_count": len(affected_pairs),
                    "cluster_count": len(clusters),
                    "clusters": clusters,
                    "likely_scope": "template, component of gedeeld contenttype",
                    "verification": (
                        "de volgende volledige crawl vindt het herhaalde signaal niet meer in "
                        "de aangepaste URL-familie"
                    ),
                },
            )
        )
    return reconcile_issues(
        db,
        website_id=website_id,
        url_id=None,
        crawl_run_id=crawl_run_id,
        snapshot_id=None,
        signals=signals,
        checked_issue_types={TEMPLATE_CLUSTER_ISSUE_TYPE},
    )


def _cluster_key(
    issue_type: str, evidence: dict[str, object], url: str
) -> str | None:
    path = _path_family(url)
    if issue_type in {"duplicate_title", "duplicate_meta_description"}:
        value = evidence.get("value")
        return f"value:{str(value).strip()}" if value else None
    if issue_type == "canonical_other_url":
        canonical = evidence.get("canonical")
        return f"canonical:{_path_family(str(canonical))}" if canonical else None
    if issue_type == "thin_content":
        return f"{evidence.get('content_level', 'unknown')}:{path}"
    if issue_type == "multiple_h1":
        return f"count:{evidence.get('count', 'unknown')}:{path}"
    return path


def _compact_evidence(evidence: dict[str, object]) -> dict[str, object]:
    """Keep diagnosis evidence useful without copying large related-URL collections."""
    allowed_keys = {
        "canonical",
        "content_level",
        "count",
        "crawl_depth",
        "threshold",
        "value",
        "word_count",
    }
    return {key: value for key, value in evidence.items() if key in allowed_keys}


def _append_cluster(
    clusters: list[dict[str, object]],
    affected_pairs: set[tuple[str, str]],
    *,
    issue_type: str,
    cluster_key: str,
    items: list[tuple[Issue, Url, dict[str, object]]],
) -> bool:
    unique_urls = sorted({url.normalized_url for _issue, url, _evidence in items})
    if len(unique_urls) < MINIMUM_CLUSTER_SIZE[issue_type]:
        return False
    affected_pairs.update((issue_type, url) for url in unique_urls)
    clusters.append(
        {
            "issue_type": issue_type,
            "cluster_key": cluster_key,
            "url_count": len(unique_urls),
            "urls": unique_urls,
            "sample_evidence": _compact_evidence(items[0][2]),
        }
    )
    return True


def _parent_cluster_key(issue_type: str, evidence: dict[str, object], url: str) -> str:
    path = _parent_path_family(url)
    if issue_type == "thin_content":
        return f"{evidence.get('content_level', 'unknown')}:{path}"
    if issue_type == "multiple_h1":
        return f"count:{evidence.get('count', 'unknown')}:{path}"
    return path


def _path_family(value: str) -> str:
    parts = [part for part in urlsplit(value).path.strip("/").split("/") if part]
    normalized = [
        "{uuid}" if UUID_RE.match(part) else NUMBER_RE.sub("{n}", part) for part in parts
    ]
    if not normalized:
        return "/"
    if len(normalized) == 1:
        return f"/{normalized[0]}"
    return "/" + "/".join(normalized[:2]) + "/*"


def _parent_path_family(value: str) -> str:
    parts = [part for part in urlsplit(value).path.strip("/").split("/") if part]
    if not parts:
        return "/"
    first = "{uuid}" if UUID_RE.match(parts[0]) else NUMBER_RE.sub("{n}", parts[0])
    return f"/{first}/*"


def _active_diagnosis_urls(
    db: Session, *, website_id: object, issue_type: str
) -> set[str]:
    diagnosis = db.scalar(
        select(Issue)
        .where(
            Issue.website_id == website_id,
            Issue.url_id.is_(None),
            Issue.issue_type == issue_type,
            Issue.status.in_(ACTIVE_STATUSES),
        )
        .order_by(Issue.last_detected_at.desc())
        .limit(1)
    )
    if diagnosis is None:
        return set()
    occurrence = db.scalar(
        select(IssueOccurrence)
        .where(IssueOccurrence.issue_id == diagnosis.id)
        .order_by(IssueOccurrence.detected_at.desc())
        .limit(1)
    )
    if occurrence is None:
        return set()
    return {
        url
        for pattern in occurrence.evidence.get("patterns", [])
        if isinstance(pattern, dict)
        for url in pattern.get("urls", [])
        if isinstance(url, str)
    }

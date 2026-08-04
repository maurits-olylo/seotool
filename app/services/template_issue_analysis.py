import hashlib
import json
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
    "canonical_chain",
    "canonical_other_url",
    "canonical_target_error",
    "canonical_target_noindex",
    "canonical_target_redirect",
    "deep_page",
    "duplicate_meta_description",
    "duplicate_title",
    "job_posting_location_incomplete",
    "job_posting_missing_application",
    "job_posting_missing_fields",
    "job_posting_remote_location_missing",
    "job_posting_schema_missing",
    "image_alt_missing",
    "functional_image_alt_empty",
    "hreflang_invalid_language",
    "hreflang_missing_return",
    "hreflang_missing_self_reference",
    "hreflang_target_canonical_mismatch",
    "hreflang_target_error",
    "hreflang_target_noindex",
    "hreflang_target_redirect",
    "missing_h1",
    "missing_meta_description",
    "multiple_broken_internal_links",
    "multiple_h1",
    "multiple_redirected_internal_links",
    "orphan_page",
    "possible_soft_404",
    "soft_404",
    "thin_content",
    "cms_link_placeholder",
    "lighthouse_cache_policy",
    "lighthouse_font_and_third_party_delivery",
    "lighthouse_image_delivery",
    "lighthouse_lcp_delivery",
    "lighthouse_render_blocking_resources",
    "lighthouse_unused_css",
    "lighthouse_unused_javascript",
    "structured_data_image_unreachable",
    "structured_data_required_fields_missing",
    "structured_data_visible_content_mismatch",
}
TEMPLATE_CLUSTER_DIAGNOSIS_TYPES = {
    TEMPLATE_CLUSTER_ISSUE_TYPE,
    *(f"{issue_type}_clusters" for issue_type in CLUSTERABLE_ISSUE_TYPES),
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
    "canonical_chain": 2,
    "canonical_other_url": 3,
    "canonical_target_error": 2,
    "canonical_target_noindex": 2,
    "canonical_target_redirect": 2,
    "deep_page": 10,
    "duplicate_meta_description": 2,
    "duplicate_title": 2,
    "job_posting_location_incomplete": 3,
    "job_posting_missing_application": 3,
    "job_posting_missing_fields": 3,
    "job_posting_remote_location_missing": 3,
    "job_posting_schema_missing": 3,
    "image_alt_missing": 2,
    "functional_image_alt_empty": 2,
    "hreflang_invalid_language": 2,
    "hreflang_missing_return": 2,
    "hreflang_missing_self_reference": 2,
    "hreflang_target_canonical_mismatch": 2,
    "hreflang_target_error": 2,
    "hreflang_target_noindex": 2,
    "hreflang_target_redirect": 2,
    "missing_h1": 5,
    "missing_meta_description": 5,
    "multiple_broken_internal_links": 2,
    "multiple_h1": 5,
    "multiple_redirected_internal_links": 2,
    "orphan_page": 2,
    "possible_soft_404": 2,
    "soft_404": 2,
    "thin_content": 5,
    "cms_link_placeholder": 2,
    "lighthouse_cache_policy": 2,
    "lighthouse_font_and_third_party_delivery": 2,
    "lighthouse_image_delivery": 2,
    "lighthouse_lcp_delivery": 2,
    "lighthouse_render_blocking_resources": 2,
    "lighthouse_unused_css": 2,
    "lighthouse_unused_javascript": 2,
    "structured_data_image_unreachable": 2,
    "structured_data_required_fields_missing": 2,
    "structured_data_visible_content_mismatch": 2,
}
HIERARCHICAL_ISSUE_TYPES = {
    "deep_page",
    "job_posting_location_incomplete",
    "job_posting_missing_application",
    "job_posting_missing_fields",
    "job_posting_remote_location_missing",
    "job_posting_schema_missing",
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
    urls_by_id = {url.id: url for url in db.scalars(select(Url).where(Url.id.in_(url_ids)))}
    pagination_urls = _active_diagnosis_urls(
        db,
        website_id=website_id,
        issue_type="pagination_series_review",
    )
    grouped: dict[tuple[str, str], list[tuple[Issue, Url, dict[str, object]]]] = defaultdict(list)
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
    covered_issue_ids: set[object] = set()
    for (issue_type, cluster_key), items in sorted(grouped.items()):
        if _append_cluster(
            clusters,
            issue_type=issue_type,
            cluster_key=cluster_key,
            items=items,
        ):
            covered_issue_ids.update(issue.id for issue, _url, _evidence in items)

    parent_groups: dict[tuple[str, str], list[tuple[Issue, Url, dict[str, object]]]] = defaultdict(
        list
    )
    for items in grouped.values():
        for item in items:
            issue, url, evidence = item
            if issue.id in covered_issue_ids or issue.issue_type not in HIERARCHICAL_ISSUE_TYPES:
                continue
            parent_key = _parent_cluster_key(issue.issue_type, evidence, url.normalized_url)
            parent_groups[(issue.issue_type, parent_key)].append(item)
    for (issue_type, cluster_key), items in sorted(parent_groups.items()):
        _append_cluster(
            clusters,
            issue_type=issue_type,
            cluster_key=cluster_key,
            items=items,
        )

    signals: list[IssueSignal] = []
    clusters_by_type: dict[str, list[dict[str, object]]] = defaultdict(list)
    for cluster in clusters:
        issue_type = cluster.get("issue_type")
        if isinstance(issue_type, str):
            clusters_by_type[issue_type].append(cluster)
    issues_by_type: dict[str, list[Issue]] = defaultdict(list)
    for issue in issues:
        issues_by_type[issue.issue_type].append(issue)
    for source_issue_type, type_clusters in sorted(clusters_by_type.items()):
        affected_urls = {
            url
            for cluster in type_clusters
            for url in cluster.get("urls", [])
            if isinstance(url, str)
        }
        sample_issue = issues_by_type[source_issue_type][0]
        signals.append(
            IssueSignal(
                issue_type=template_cluster_diagnosis_type(source_issue_type),
                category=sample_issue.category,
                severity=_highest_severity(issues_by_type[source_issue_type]),
                confidence="high",
                title=(
                    f"{len(affected_urls)} URL-signalen voor "
                    f"'{sample_issue.title}' vormen {len(type_clusters)} clusters"
                ),
                description=(
                    "Dit specifieke signaal komt terug binnen herkenbare URL-families of gebruikt "
                    "dezelfde bewijswaarde. Het wordt daarom als één gerichte templatecontrole "
                    "getoond in plaats van als losse taak per URL."
                ),
                recommended_action=(
                    "Beoordeel de clusters voor dit issuetype op template-, component- of "
                    "contenttypeniveau. Pas alleen aantoonbaar onbedoelde patronen centraal aan. "
                    f"Onderliggende actie: {sample_issue.recommended_action}"
                ),
                evidence={
                    "source_issue_type": source_issue_type,
                    "affected_signal_count": len(affected_urls),
                    "cluster_count": len(type_clusters),
                    "clusters": type_clusters,
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
        checked_issue_types=TEMPLATE_CLUSTER_DIAGNOSIS_TYPES,
    )


def template_cluster_diagnosis_type(source_issue_type: str) -> str:
    return f"{source_issue_type}_clusters"


def _highest_severity(issues: list[Issue]) -> str:
    rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    return max(issues, key=lambda issue: rank.get(issue.severity, 0)).severity


def _cluster_key(issue_type: str, evidence: dict[str, object], url: str) -> str | None:
    path = _path_family(url)
    if issue_type in {"duplicate_title", "duplicate_meta_description"}:
        value = evidence.get("value")
        return f"value:{str(value).strip()}" if value else None
    if issue_type == "canonical_other_url":
        canonical = evidence.get("canonical")
        return f"canonical:{_path_family(str(canonical))}" if canonical else None
    if issue_type == "cms_link_placeholder":
        return f"elements:{evidence.get('element_count', 0)}:{path}"
    if issue_type.startswith("lighthouse_"):
        cause_key = evidence.get("cause_key")
        return f"cause:{cause_key}" if cause_key else path
    if issue_type.startswith("structured_data_"):
        cause_key = evidence.get("cause_key")
        return f"cause:{cause_key}" if cause_key else path
    if issue_type == "job_posting_missing_fields":
        fields = evidence.get("missing_fields", [])
        if not isinstance(fields, list):
            fields = []
        return f"fields:{','.join(sorted(str(field) for field in fields))}:{path}"
    if issue_type in {
        "multiple_broken_internal_links",
        "multiple_redirected_internal_links",
    }:
        targets = _component_targets(issue_type, evidence)
        if not targets:
            return None
        digest = hashlib.sha256(json.dumps(targets).encode()).hexdigest()[:16]
        return f"targets:{digest}"
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
        "incoming_internal_pages",
        "is_important",
        "image_urls",
        "missing_fields",
        "review_reason",
        "source",
        "threshold",
        "value",
        "word_count",
        "audit_ids",
        "cause_key",
        "potential_savings_ms",
        "resources",
        "strategy",
        "wasted_bytes",
        "images",
        "mismatches",
        "schemas",
    }
    return {key: value for key, value in evidence.items() if key in allowed_keys}


def _append_cluster(
    clusters: list[dict[str, object]],
    *,
    issue_type: str,
    cluster_key: str,
    items: list[tuple[Issue, Url, dict[str, object]]],
) -> bool:
    unique_urls = sorted({url.normalized_url for _issue, url, _evidence in items})
    if len(unique_urls) < MINIMUM_CLUSTER_SIZE[issue_type]:
        return False
    clusters.append(
        {
            "issue_type": issue_type,
            "cluster_key": cluster_key,
            "url_count": len(unique_urls),
            "urls": unique_urls,
            "issue_ids": sorted(str(issue.id) for issue, _url, _evidence in items),
            "sample_evidence": _compact_evidence(items[0][2]),
            **(
                {"shared_targets": _component_targets(issue_type, items[0][2])}
                if issue_type
                in {
                    "multiple_broken_internal_links",
                    "multiple_redirected_internal_links",
                }
                else {}
            ),
        }
    )
    return True


def _component_targets(issue_type: str, evidence: dict[str, object]) -> list[str]:
    evidence_key, target_key = (
        ("broken_links", "target_url")
        if issue_type == "multiple_broken_internal_links"
        else ("redirected_links", "redirect_url")
    )
    values = evidence.get(evidence_key, [])
    return sorted(
        {
            str(item[target_key])
            for item in values
            if isinstance(item, dict) and isinstance(item.get(target_key), str)
        }
    )


def _parent_cluster_key(issue_type: str, evidence: dict[str, object], url: str) -> str:
    path = _parent_path_family(url)
    if issue_type == "job_posting_missing_fields":
        fields = evidence.get("missing_fields", [])
        if not isinstance(fields, list):
            fields = []
        return f"fields:{','.join(sorted(str(field) for field in fields))}:{path}"
    if issue_type == "thin_content":
        return f"{evidence.get('content_level', 'unknown')}:{path}"
    if issue_type == "multiple_h1":
        return f"count:{evidence.get('count', 'unknown')}:{path}"
    return path


def _path_family(value: str) -> str:
    parts = [part for part in urlsplit(value).path.strip("/").split("/") if part]
    normalized = ["{uuid}" if UUID_RE.match(part) else NUMBER_RE.sub("{n}", part) for part in parts]
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


def _active_diagnosis_urls(db: Session, *, website_id: object, issue_type: str) -> set[str]:
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

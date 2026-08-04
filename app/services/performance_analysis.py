from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from app.models.crawl import UrlSnapshot
from app.models.discovery import Url
from app.models.performance import PerformanceObservation
from app.services.url_filtering import is_probable_html_page

MAX_PERFORMANCE_CANDIDATES = 10
MAX_FAILED_AUDITS = 20
MAX_AUDIT_ITEMS = 5
LAB_METRIC_AUDITS = {
    "cumulative-layout-shift",
    "first-contentful-paint",
    "largest-contentful-paint",
    "speed-index",
    "total-blocking-time",
}


@dataclass(frozen=True)
class PerformanceCandidate:
    url: Url
    snapshot: UrlSnapshot
    reasons: tuple[str, ...]


def select_performance_candidates(
    records: list[tuple[Url, UrlSnapshot]],
    *,
    active_issue_url_ids: set[object] | None = None,
    changed_url_ids: set[object] | None = None,
    limit: int = MAX_PERFORMANCE_CANDIDATES,
) -> list[PerformanceCandidate]:
    """Select a small, risk-led and template-diverse PageSpeed sample."""
    if limit <= 0:
        return []
    bounded_limit = min(limit, MAX_PERFORMANCE_CANDIDATES)
    issue_ids = active_issue_url_ids or set()
    changed_ids = changed_url_ids or set()
    eligible: list[PerformanceCandidate] = []
    for url, snapshot in records:
        reasons = _candidate_reasons(url, snapshot, issue_ids, changed_ids)
        if reasons:
            eligible.append(PerformanceCandidate(url, snapshot, reasons))
    eligible.sort(
        key=lambda item: (
            0 if "important_url" in item.reasons else 1,
            0 if "active_issue" in item.reasons else 1,
            0 if "recent_change" in item.reasons else 1,
            item.url.normalized_url,
        )
    )
    selected: list[PerformanceCandidate] = []
    seen_templates: set[str] = set()
    for candidate in eligible:
        template = _template_key(candidate.url.normalized_url)
        if template in seen_templates:
            continue
        selected.append(candidate)
        seen_templates.add(template)
        if len(selected) >= bounded_limit:
            return selected
    for candidate in eligible:
        if candidate in selected:
            continue
        selected.append(candidate)
        if len(selected) >= bounded_limit:
            break
    return selected


def observation_from_pagespeed_response(
    *,
    website_id: object,
    url_id: object,
    requested_url: str,
    strategy: str,
    payload: dict[str, object],
    analyzed_at: datetime | None = None,
) -> PerformanceObservation:
    if strategy not in {"mobile", "desktop"}:
        raise ValueError("PageSpeed strategy must be mobile or desktop")
    lighthouse = _mapping(payload.get("lighthouseResult"))
    categories = _mapping(lighthouse.get("categories"))
    audits = _mapping(lighthouse.get("audits"))
    loading = _mapping(payload.get("loadingExperience"))
    origin_loading = _mapping(payload.get("originLoadingExperience"))
    return PerformanceObservation(
        website_id=website_id,
        url_id=url_id,
        analyzed_at=analyzed_at or datetime.now(UTC),
        strategy=strategy,
        status="succeeded",
        requested_url=requested_url,
        final_url=_string(lighthouse.get("finalDisplayedUrl") or lighthouse.get("finalUrl")),
        lighthouse_version=_string(lighthouse.get("lighthouseVersion")),
        fetch_time=_timestamp(lighthouse.get("fetchTime")),
        category_scores={
            name: _number(_mapping(value).get("score")) for name, value in categories.items()
        },
        lab_metrics={
            audit_id: _compact_metric(_mapping(audits[audit_id]))
            for audit_id in sorted(LAB_METRIC_AUDITS & audits.keys())
        },
        field_metrics=_field_metrics(loading),
        origin_field_metrics=_field_metrics(origin_loading),
        failed_audits=_failed_audits(audits),
        field_scope="url" if _mapping(loading.get("metrics")) else None,
        collection_period_days=_collection_period_days(loading),
    )


def _candidate_reasons(
    url: Url,
    snapshot: UrlSnapshot,
    issue_ids: set[object],
    changed_ids: set[object],
) -> tuple[str, ...]:
    content_type = (snapshot.content_type or "").lower()
    if not (
        url.is_active
        and snapshot.status_code == 200
        and not snapshot.redirect_chain
        and ("html" in content_type or not content_type)
        and is_probable_html_page(url.normalized_url)
    ):
        return ()
    reasons: list[str] = []
    if url.is_important:
        reasons.append("important_url")
    if url.id in issue_ids:
        reasons.append("active_issue")
    if url.id in changed_ids:
        reasons.append("recent_change")
    return tuple(reasons)


def _template_key(url: str) -> str:
    parts = [part for part in urlsplit(url).path.split("/") if part]
    return parts[0].lower() if parts else "/"


def _failed_audits(audits: dict[str, Any]) -> list[dict[str, object]]:
    failed: list[dict[str, object]] = []
    for audit_id, raw in audits.items():
        audit = _mapping(raw)
        score = _number(audit.get("score"))
        if score is None or score >= 1:
            continue
        details = _mapping(audit.get("details"))
        items = details.get("items")
        compact_items = [
            _compact_item(item) for item in items[:MAX_AUDIT_ITEMS] if isinstance(item, dict)
        ] if isinstance(items, list) else []
        failed.append(
            {
                "audit_id": audit_id,
                "title": _string(audit.get("title")),
                "score": score,
                "display_value": _string(audit.get("displayValue")),
                "numeric_value": _number(audit.get("numericValue")),
                "numeric_unit": _string(audit.get("numericUnit")),
                "items": compact_items,
            }
        )
    failed.sort(key=lambda item: (float(item["score"]), str(item["audit_id"])))
    return failed[:MAX_FAILED_AUDITS]


def _compact_item(item: dict[str, object]) -> dict[str, object]:
    allowed = {"url", "totalBytes", "wastedBytes", "wastedMs", "node", "source"}
    return {key: item[key] for key in allowed if key in item}


def _compact_metric(audit: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in {
            "score": _number(audit.get("score")),
            "numeric_value": _number(audit.get("numericValue")),
            "numeric_unit": _string(audit.get("numericUnit")),
            "display_value": _string(audit.get("displayValue")),
        }.items()
        if value is not None
    }


def _field_metrics(experience: dict[str, object]) -> dict[str, object]:
    metrics = _mapping(experience.get("metrics"))
    return {
        name: {
            key: value
            for key, value in {
                "percentile": _number(_mapping(metric).get("percentile")),
                "category": _string(_mapping(metric).get("category")),
                "distributions": _mapping(metric).get("distributions", []),
            }.items()
            if value not in (None, [])
        }
        for name, metric in metrics.items()
    }


def _collection_period_days(experience: dict[str, object]) -> int | None:
    period = _mapping(experience.get("collectionPeriod"))
    first = _date_parts(_mapping(period.get("firstDate")))
    last = _date_parts(_mapping(period.get("lastDate")))
    return (last - first).days + 1 if first and last and last >= first else None


def _date_parts(value: dict[str, object]):  # type: ignore[no-untyped-def]
    try:
        return datetime(int(value["year"]), int(value["month"]), int(value["day"])).date()
    except (KeyError, TypeError, ValueError):
        return None


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string(value: object) -> str | None:
    return str(value) if value is not None else None


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def _timestamp(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
    except ValueError:
        return None

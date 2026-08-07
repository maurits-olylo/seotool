from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.content_analysis import UrlContentClassification
from app.models.crawl import UrlSnapshot
from app.models.discovery import Url
from app.models.integrations import SearchConsoleMetric
from app.models.issues import Issue
from app.models.opportunities import OpportunityEvaluation
from app.services.discovery_pages import is_discovery_only_page
from app.services.opportunity_scoring import (
    OpportunityScores,
    calculate_opportunity_scores,
    store_opportunity_evaluation,
)

ACTIVE_ISSUE_STATUSES = {
    "new",
    "review",
    "accepted",
    "planned",
    "in_progress",
    "waiting_for_client",
}
CTR_FRICTIONS = {
    "missing_title",
    "duplicate_title",
    "missing_meta_description",
    "duplicate_meta_description",
}
PAGE_TWO_FRICTIONS = {"thin_content", "near_duplicate_content"}
INTERNAL_LINK_FRICTIONS = {"deep_page", "important_page_few_internal_links"}
MINIMUM_PERIOD_DAYS = 28
PATTERN_VERSION = "opportunity-patterns-2026-08-07-v1"


@dataclass
class PageMetrics:
    clicks: float = 0
    impressions: int = 0
    weighted_position: float = 0

    @property
    def ctr(self) -> float:
        return self.clicks / self.impressions if self.impressions else 0

    @property
    def position(self) -> float:
        return self.weighted_position / self.impressions if self.impressions else 0


def _metrics_by_url(
    db: Session, website_id: UUID, period_start: date, period_end: date
) -> dict[UUID, PageMetrics]:
    totals: dict[UUID, PageMetrics] = defaultdict(PageMetrics)
    rows = db.execute(
        select(
            SearchConsoleMetric.url_id,
            SearchConsoleMetric.clicks,
            SearchConsoleMetric.impressions,
            SearchConsoleMetric.position,
        ).where(
            SearchConsoleMetric.website_id == website_id,
            SearchConsoleMetric.date >= period_start,
            SearchConsoleMetric.date <= period_end,
            SearchConsoleMetric.url_id.is_not(None),
        )
    )
    for url_id, clicks, impressions, position in rows:
        count = int(impressions or 0)
        totals[url_id].clicks += float(clicks or 0)
        totals[url_id].impressions += count
        totals[url_id].weighted_position += float(position or 0) * count
    return totals


def _issues_by_url(db: Session, website_id: UUID) -> dict[UUID, list[Issue]]:
    grouped: dict[UUID, list[Issue]] = defaultdict(list)
    issues = db.scalars(
        select(Issue).where(
            Issue.website_id == website_id,
            Issue.url_id.is_not(None),
            Issue.status.in_(ACTIVE_ISSUE_STATUSES),
        )
    )
    for issue in issues:
        if issue.url_id:
            grouped[issue.url_id].append(issue)
    return grouped


def _latest_canonicals(db: Session, url_ids: set[UUID]) -> dict[UUID, str | None]:
    if not url_ids:
        return {}
    snapshots = db.scalars(
        select(UrlSnapshot)
        .where(UrlSnapshot.url_id.in_(url_ids))
        .order_by(UrlSnapshot.checked_at.desc())
    )
    result: dict[UUID, str | None] = {}
    for snapshot in snapshots:
        result.setdefault(snapshot.url_id, snapshot.canonical)
    return result


def _latest_classifications(db: Session, website_id: UUID) -> dict[UUID, UrlContentClassification]:
    rows = db.scalars(
        select(UrlContentClassification)
        .where(UrlContentClassification.website_id == website_id)
        .order_by(UrlContentClassification.created_at.desc())
    )
    result: dict[UUID, UrlContentClassification] = {}
    for row in rows:
        result.setdefault(row.url_id, row)
    return result


def _score_potential(impressions: int, *, threshold: int) -> float:
    return min(100.0, round(40 + 60 * max(0, impressions - threshold) / (threshold * 3), 2))


def _evidence_score(impressions: int, period_days: int, *, threshold: int) -> float:
    volume = min(35.0, 20 + 15 * impressions / (threshold * 2))
    duration = min(25.0, 25 * period_days / MINIMUM_PERIOD_DAYS)
    return round(min(100.0, 40 + volume + duration), 2)


def _contributors(
    pattern: str, metrics: PageMetrics, issues: list[Issue]
) -> list[dict[str, object]]:
    return [
        {
            "dimension": "potential",
            "signal": "gsc_impressions",
            "value": metrics.impressions,
            "direction": "positive",
        },
        {
            "dimension": "potential",
            "signal": "gsc_position",
            "value": round(metrics.position, 2),
            "direction": "context",
        },
        {
            "dimension": "friction",
            "signal": "active_issue_types",
            "value": sorted(issue.issue_type for issue in issues),
            "direction": "negative",
        },
        {
            "dimension": "evidence",
            "signal": "pattern_version",
            "value": f"{PATTERN_VERSION}:{pattern}",
            "direction": "context",
        },
    ]


def _store_pattern(
    db: Session,
    *,
    website_id: UUID,
    url: Url,
    period_start: date,
    period_end: date,
    pattern: str,
    metrics: PageMetrics,
    matching_issues: list[Issue],
    scores: OpportunityScores,
) -> tuple[OpportunityEvaluation, bool]:
    return store_opportunity_evaluation(
        db,
        website_id=website_id,
        primary_url_id=url.id,
        scope_type="page",
        scope_key=f"{pattern}:{url.id}",
        period_start=period_start,
        period_end=period_end,
        scores=scores,
        source_coverage={
            "gsc": True,
            "crawler_issues": True,
            "analytics": False,
            "pattern": pattern,
        },
        contributors=_contributors(pattern, metrics, matching_issues),
        evidence=[
            {
                "source": "gsc",
                "clicks": round(metrics.clicks, 2),
                "impressions": metrics.impressions,
                "ctr": round(metrics.ctr, 4),
                "position": round(metrics.position, 2),
            },
            {
                "source": "issues",
                "issue_ids": [str(issue.id) for issue in matching_issues],
                "issue_types": sorted(issue.issue_type for issue in matching_issues),
            },
        ],
    )


def evaluate_website_opportunities(
    db: Session, website_id: UUID, period_start: date, period_end: date
) -> dict[str, int]:
    period_days = (period_end - period_start).days + 1
    if period_days < MINIMUM_PERIOD_DAYS:
        raise ValueError(f"Opportunity periods must contain at least {MINIMUM_PERIOD_DAYS} days")
    metrics_by_url = _metrics_by_url(db, website_id, period_start, period_end)
    issues_by_url = _issues_by_url(db, website_id)
    urls = {
        url.id: url
        for url in db.scalars(
            select(Url).where(
                Url.website_id == website_id,
                Url.id.in_(set(metrics_by_url)),
                Url.is_active.is_(True),
                Url.is_indexable.is_(True),
                Url.current_status_code == 200,
            )
        )
    }
    canonicals = _latest_canonicals(db, set(urls))
    classifications = _latest_classifications(db, website_id)
    created = 0
    existing = 0
    skipped = len(metrics_by_url) - len(urls)

    for url_id, url in urls.items():
        if is_discovery_only_page(url.normalized_url, canonicals.get(url_id)):
            skipped += 1
            continue
        metrics = metrics_by_url[url_id]
        issues = issues_by_url.get(url_id, [])
        issue_types = {issue.issue_type for issue in issues}
        candidates: list[tuple[str, set[str], OpportunityScores]] = []

        if (
            metrics.impressions >= 250
            and 4 <= metrics.position <= 15
            and metrics.ctr < 0.025
            and issue_types & CTR_FRICTIONS
        ):
            candidates.append(
                (
                    "ctr",
                    CTR_FRICTIONS,
                    calculate_opportunity_scores(
                        potential=_score_potential(metrics.impressions, threshold=250),
                        friction=75,
                        evidence=_evidence_score(metrics.impressions, period_days, threshold=250),
                        feasibility=85,
                    ),
                )
            )

        classification = classifications.get(url_id)
        if (
            metrics.impressions >= 150
            and 11 <= metrics.position <= 20
            and issue_types & PAGE_TWO_FRICTIONS
            and classification
            and classification.confidence >= 0.65
            and classification.search_intent not in {"uncertain", "mixed"}
        ):
            candidates.append(
                (
                    "page_two",
                    PAGE_TWO_FRICTIONS,
                    calculate_opportunity_scores(
                        potential=_score_potential(metrics.impressions, threshold=150),
                        friction=70,
                        evidence=_evidence_score(metrics.impressions, period_days, threshold=150),
                        feasibility=60,
                    ),
                )
            )

        if (
            metrics.impressions >= 150
            and (url.crawl_depth or 0) >= 4
            and issue_types & INTERNAL_LINK_FRICTIONS
        ):
            candidates.append(
                (
                    "internal_link",
                    INTERNAL_LINK_FRICTIONS,
                    calculate_opportunity_scores(
                        potential=_score_potential(metrics.impressions, threshold=150),
                        friction=min(90, 55 + (url.crawl_depth or 0) * 5),
                        evidence=_evidence_score(metrics.impressions, period_days, threshold=150),
                        feasibility=80,
                    ),
                )
            )

        for pattern, relevant_types, scores in candidates:
            relevant = [issue for issue in issues if issue.issue_type in relevant_types]
            _evaluation, was_created = _store_pattern(
                db,
                website_id=website_id,
                url=url,
                period_start=period_start,
                period_end=period_end,
                pattern=pattern,
                metrics=metrics,
                matching_issues=relevant,
                scores=scores,
            )
            created += int(was_created)
            existing += int(not was_created)
    db.commit()
    return {"created": created, "existing": existing, "skipped": skipped}

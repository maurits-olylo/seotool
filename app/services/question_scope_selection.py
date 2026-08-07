import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.content_analysis import UrlContentClassification
from app.models.discovery import Url
from app.models.integrations import SearchConsoleQueryMetric
from app.services.content_analysis import normalize_query
from app.services.question_coverage import is_question_like


@dataclass
class QueryPerformance:
    clicks: float = 0
    impressions: int = 0
    position_weight: float = 0

    @property
    def position(self) -> float:
        return self.position_weight / self.impressions if self.impressions else 0


@dataclass(frozen=True)
class QuestionScopeCandidate:
    url_id: UUID
    url: str
    family: str
    question: str
    clicks: float
    impressions: int
    position: float
    selection_priority: float
    contributors: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class QuestionScopeSelection:
    candidates: tuple[QuestionScopeCandidate, ...]
    eligible_pages: int
    eligible_questions: int
    selected_pages: int
    selected_families: int
    limits: dict[str, int]


def url_family(url: Url) -> str:
    if url.page_type:
        return f"page_type:{url.page_type}"
    segments = [part for part in urlsplit(url.normalized_url).path.split("/") if part]
    if not segments:
        return "path:/"
    first = re.sub(r"\d+", "#", segments[0].lower())
    return f"path:{first}:depth-{len(segments)}"


def _latest_roles(db: Session, website_id: UUID) -> dict[UUID, str]:
    roles: dict[UUID, str] = {}
    rows = db.scalars(
        select(UrlContentClassification)
        .where(UrlContentClassification.website_id == website_id)
        .order_by(UrlContentClassification.created_at.desc())
    )
    for row in rows:
        roles.setdefault(row.url_id, row.content_role)
    return roles


def _priority(
    *,
    performance: QueryPerformance,
    url: Url,
    content_role: str | None,
) -> tuple[float, tuple[dict[str, object], ...]]:
    demand = min(55.0, math.log1p(performance.impressions) * 8)
    engagement = min(15.0, performance.clicks * 1.5)
    strategic = 15.0 if url.is_important else 0.0
    role = 10.0 if content_role in {"convert", "support_choice", "provide_proof"} else 0.0
    opportunity = 5.0 if 4 <= performance.position <= 30 else 0.0
    contributors = (
        {"signal": "gsc_impressions", "value": performance.impressions, "points": round(demand, 2)},
        {"signal": "gsc_clicks", "value": round(performance.clicks, 1), "points": engagement},
        {"signal": "important_page", "value": url.is_important, "points": strategic},
        {"signal": "content_role", "value": content_role, "points": role},
        {
            "signal": "opportunity_position",
            "value": round(performance.position, 1),
            "points": opportunity,
        },
    )
    return round(min(100.0, demand + engagement + strategic + role + opportunity), 2), contributors


def select_question_scopes(
    db: Session,
    *,
    website_id: UUID,
    period_start: date,
    period_end: date,
    max_pages: int = 25,
    max_questions_per_page: int = 3,
    max_pages_per_family: int = 5,
    max_total: int = 60,
    minimum_impressions: int = 25,
) -> QuestionScopeSelection:
    limits = {
        "max_pages": max_pages,
        "max_questions_per_page": max_questions_per_page,
        "max_pages_per_family": max_pages_per_family,
        "max_total": max_total,
        "minimum_impressions": minimum_impressions,
    }
    if any(value < 1 for value in limits.values()):
        raise ValueError("Question scope limits must be positive")

    urls = {
        item.id: item
        for item in db.scalars(
            select(Url).where(
                Url.website_id == website_id,
                Url.is_active.is_(True),
                Url.is_indexable.is_(True),
                Url.current_status_code.between(200, 299),
            )
        )
    }
    roles = _latest_roles(db, website_id)
    totals: dict[tuple[UUID, str], QueryPerformance] = defaultdict(QueryPerformance)
    rows = db.execute(
        select(
            SearchConsoleQueryMetric.url_id,
            SearchConsoleQueryMetric.query,
            SearchConsoleQueryMetric.clicks,
            SearchConsoleQueryMetric.impressions,
            SearchConsoleQueryMetric.position,
        ).where(
            SearchConsoleQueryMetric.website_id == website_id,
            SearchConsoleQueryMetric.date >= period_start,
            SearchConsoleQueryMetric.date <= period_end,
            SearchConsoleQueryMetric.url_id.is_not(None),
        )
    )
    for url_id, query, clicks, impressions, position in rows:
        normalized = normalize_query(str(query))
        if url_id not in urls or not is_question_like(normalized):
            continue
        performance = totals[(url_id, normalized)]
        performance.clicks += float(clicks or 0)
        performance.impressions += int(impressions or 0)
        performance.position_weight += float(position or 0) * int(impressions or 0)

    per_page: dict[UUID, list[QuestionScopeCandidate]] = defaultdict(list)
    for (url_id, question), performance in totals.items():
        if performance.impressions < minimum_impressions:
            continue
        url = urls[url_id]
        priority, contributors = _priority(
            performance=performance,
            url=url,
            content_role=roles.get(url_id),
        )
        per_page[url_id].append(
            QuestionScopeCandidate(
                url_id=url_id,
                url=url.normalized_url,
                family=url_family(url),
                question=question,
                clicks=round(performance.clicks, 1),
                impressions=performance.impressions,
                position=round(performance.position, 1),
                selection_priority=priority,
                contributors=contributors,
            )
        )

    for candidates in per_page.values():
        candidates.sort(key=lambda item: (-item.selection_priority, item.question))
    ranked_pages = sorted(
        per_page,
        key=lambda url_id: (
            -per_page[url_id][0].selection_priority,
            urls[url_id].normalized_url,
        ),
    )
    selected: list[QuestionScopeCandidate] = []
    selected_pages: set[UUID] = set()
    family_pages: dict[str, set[UUID]] = defaultdict(set)
    for url_id in ranked_pages:
        family = url_family(urls[url_id])
        if len(selected_pages) >= max_pages or len(family_pages[family]) >= max_pages_per_family:
            continue
        for candidate in per_page[url_id][:max_questions_per_page]:
            if len(selected) >= max_total:
                break
            selected.append(candidate)
        if selected and selected[-1].url_id == url_id:
            selected_pages.add(url_id)
            family_pages[family].add(url_id)
        if len(selected) >= max_total:
            break

    return QuestionScopeSelection(
        candidates=tuple(selected),
        eligible_pages=len(per_page),
        eligible_questions=sum(len(items) for items in per_page.values()),
        selected_pages=len(selected_pages),
        selected_families=len(family_pages),
        limits=limits,
    )

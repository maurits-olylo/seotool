from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integrations import SearchConsoleQueryMetric


@dataclass
class QueryPageTotals:
    clicks: float = 0
    impressions: int = 0
    position_weight: float = 0

    @property
    def ctr(self) -> float:
        return self.clicks / self.impressions if self.impressions else 0

    @property
    def position(self) -> float:
        return self.position_weight / self.impressions if self.impressions else 0


def _add_metric(target: QueryPageTotals, clicks: float, impressions: int, position: float) -> None:
    target.clicks += clicks
    target.impressions += impressions
    target.position_weight += position * impressions


def build_search_insights(
    db: Session,
    website_id: UUID,
    start: date,
    end: date,
    previous_start: date,
    previous_end: date,
) -> list[dict[str, object]]:
    """Return practical GSC query/page opportunities for a report period."""
    rows = db.execute(
        select(
            SearchConsoleQueryMetric.date,
            SearchConsoleQueryMetric.query,
            SearchConsoleQueryMetric.page_url,
            SearchConsoleQueryMetric.clicks,
            SearchConsoleQueryMetric.impressions,
            SearchConsoleQueryMetric.position,
        ).where(
            SearchConsoleQueryMetric.website_id == website_id,
            SearchConsoleQueryMetric.date >= previous_start,
            SearchConsoleQueryMetric.date <= end,
        )
    )
    current: dict[tuple[str, str], QueryPageTotals] = defaultdict(QueryPageTotals)
    previous: dict[tuple[str, str], QueryPageTotals] = defaultdict(QueryPageTotals)
    for metric_date, query, page_url, clicks, impressions, position in rows:
        key = (str(query), str(page_url))
        if start <= metric_date <= end:
            _add_metric(current[key], float(clicks or 0), int(impressions or 0), float(position or 0))
        elif previous_start <= metric_date <= previous_end:
            _add_metric(previous[key], float(clicks or 0), int(impressions or 0), float(position or 0))

    insights: list[dict[str, object]] = []
    current_by_query: dict[str, list[tuple[str, QueryPageTotals]]] = defaultdict(list)
    for (query, page_url), totals in current.items():
        if totals.impressions:
            current_by_query[query].append((page_url, totals))

    cannibalization_candidates = []
    for query, pages in current_by_query.items():
        meaningful_pages = [item for item in pages if item[1].impressions >= 10]
        impressions = sum(item[1].impressions for item in meaningful_pages)
        if len(meaningful_pages) >= 2 and impressions >= 100:
            cannibalization_candidates.append((impressions, query, meaningful_pages))
    for impressions, query, pages in sorted(cannibalization_candidates, reverse=True)[:2]:
        top_pages = sorted(pages, key=lambda item: item[1].impressions, reverse=True)[:3]
        insights.append(
            {
                "type": "cannibalization",
                "title": f'Zoekopdracht "{query}" komt op meerdere pagina’s voor',
                "description": (
                    f"{len(pages)} pagina’s delen samen {impressions:,} vertoningen. "
                    "Bepaal welke pagina de primaire bestemming moet zijn."
                ),
                "query": query,
                "pages": [
                    {
                        "url": page_url,
                        "clicks": round(totals.clicks, 1),
                        "impressions": totals.impressions,
                        "ctr": round(totals.ctr * 100, 1),
                        "position": round(totals.position, 1),
                    }
                    for page_url, totals in top_pages
                ],
            }
        )

    ctr_candidates = [
        (totals.impressions, query, page_url, totals)
        for (query, page_url), totals in current.items()
        if totals.impressions >= 250 and 3 <= totals.position <= 15 and totals.ctr < 0.025
    ]
    for impressions, query, page_url, totals in sorted(ctr_candidates, reverse=True)[:2]:
        insights.append(
            {
                "type": "ctr_opportunity",
                "title": f'CTR-kans voor "{query}"',
                "description": (
                    f"{impressions:,} vertoningen, {totals.ctr * 100:.1f}% CTR en "
                    f"gemiddelde positie {totals.position:.1f}. Controleer title en meta description."
                ),
                "query": query,
                "url": page_url,
                "clicks": round(totals.clicks, 1),
                "impressions": totals.impressions,
                "ctr": round(totals.ctr * 100, 1),
                "position": round(totals.position, 1),
            }
        )

    decline_candidates = []
    for key, old_totals in previous.items():
        new_totals = current.get(key, QueryPageTotals())
        if old_totals.clicks >= 10 and new_totals.clicks <= old_totals.clicks * 0.75:
            decline_candidates.append((old_totals.clicks - new_totals.clicks, key, old_totals, new_totals))
    for _, (query, page_url), old_totals, new_totals in sorted(decline_candidates, reverse=True)[:2]:
        change = round((new_totals.clicks - old_totals.clicks) / old_totals.clicks * 100, 1)
        insights.append(
            {
                "type": "declining_query",
                "title": f'Zoekopdracht "{query}" verliest klikken',
                "description": (
                    f"Van {old_totals.clicks:,.0f} naar {new_totals.clicks:,.0f} klikken "
                    f"({change:.1f}%) op deze landingspagina."
                ),
                "query": query,
                "url": page_url,
                "previous_clicks": round(old_totals.clicks, 1),
                "clicks": round(new_totals.clicks, 1),
                "change_percent": change,
            }
        )

    return insights[:6]

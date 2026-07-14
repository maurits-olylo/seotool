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
            _add_metric(
                current[key], float(clicks or 0), int(impressions or 0), float(position or 0)
            )
        elif previous_start <= metric_date <= previous_end:
            _add_metric(
                previous[key], float(clicks or 0), int(impressions or 0), float(position or 0)
            )

    insights: list[dict[str, object]] = []
    current_by_query: dict[str, list[tuple[str, QueryPageTotals]]] = defaultdict(list)
    previous_by_query: dict[str, list[tuple[str, QueryPageTotals]]] = defaultdict(list)
    for (query, page_url), totals in current.items():
        if totals.impressions:
            current_by_query[query].append((page_url, totals))
    for (query, page_url), totals in previous.items():
        if totals.impressions:
            previous_by_query[query].append((page_url, totals))

    switched_queries: set[str] = set()
    switching_candidates = []
    for query, current_pages in current_by_query.items():
        previous_pages = previous_by_query.get(query, [])
        current_total = sum(item[1].impressions for item in current_pages)
        previous_total = sum(item[1].impressions for item in previous_pages)
        if current_total < 100 or previous_total < 100:
            continue
        current_top = max(current_pages, key=lambda item: item[1].impressions)
        previous_top = max(previous_pages, key=lambda item: item[1].impressions)
        current_share = current_top[1].impressions / current_total
        previous_share = previous_top[1].impressions / previous_total
        if current_top[0] != previous_top[0] and current_share >= 0.55 and previous_share >= 0.55:
            switching_candidates.append(
                (
                    current_total + previous_total,
                    query,
                    previous_top,
                    current_top,
                    previous_share,
                    current_share,
                )
            )

    for _, query, old_page, new_page, old_share, new_share in sorted(
        switching_candidates, reverse=True
    )[:3]:
        switched_queries.add(query)
        insights.append(
            {
                "type": "ranking_url_changed",
                "title": f'Dominante landingspagina voor "{query}" is gewisseld',
                "description": (
                    f"De vorige URL had {old_share * 100:.0f}% van de vertoningen; "
                    f"de huidige URL heeft {new_share * 100:.0f}%. Controleer of dit "
                    "de bedoelde primaire pagina is."
                ),
                "query": query,
                "previous_url": old_page[0],
                "url": new_page[0],
                "pages": [
                    {
                        "label": "Vorige dominante URL",
                        "url": old_page[0],
                        "clicks": round(old_page[1].clicks, 1),
                        "impressions": old_page[1].impressions,
                        "ctr": round(old_page[1].ctr * 100, 1),
                        "position": round(old_page[1].position, 1),
                    },
                    {
                        "label": "Huidige dominante URL",
                        "url": new_page[0],
                        "clicks": round(new_page[1].clicks, 1),
                        "impressions": new_page[1].impressions,
                        "ctr": round(new_page[1].ctr * 100, 1),
                        "position": round(new_page[1].position, 1),
                    },
                ],
            }
        )

    cannibalization_candidates = []
    for query, pages in current_by_query.items():
        if query in switched_queries:
            continue
        meaningful_pages = [item for item in pages if item[1].impressions >= 10]
        impressions = sum(item[1].impressions for item in meaningful_pages)
        ranked_pages = sorted(
            meaningful_pages,
            key=lambda item: item[1].impressions,
            reverse=True,
        )
        second_page_share = (
            ranked_pages[1][1].impressions / impressions
            if len(ranked_pages) >= 2 and impressions
            else 0
        )
        if len(meaningful_pages) >= 2 and impressions >= 100 and second_page_share >= 0.2:
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
                    f"gemiddelde positie {totals.position:.1f}. Controleer title en "
                    "meta description."
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
            decline_candidates.append(
                (old_totals.clicks - new_totals.clicks, key, old_totals, new_totals)
            )
    for _, (query, page_url), old_totals, new_totals in sorted(decline_candidates, reverse=True)[
        :2
    ]:
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

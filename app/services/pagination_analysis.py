from collections import defaultdict
from urllib.parse import parse_qsl, urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crawl import UrlSnapshot
from app.models.discovery import Url
from app.models.issues import Issue
from app.services.issue_engine import reconcile_issues
from app.services.technical_checks import IssueSignal

PAGINATION_PARAMETERS = {"page", "paged", "p", "offset", "start"}
PAGINATION_SERIES_ISSUE_TYPE = "pagination_series_review"
PAGINATION_CHILD_ISSUE_TYPES = {
    "canonical_other_url",
    "deep_page",
    "duplicate_meta_description",
    "duplicate_title",
}
ACTIVE_STATUSES = {
    "new",
    "review",
    "accepted",
    "planned",
    "in_progress",
    "waiting_for_client",
}


def analyze_pagination_series(
    db: Session, *, website_id: object, crawl_run_id: object
) -> list[Issue]:
    """Group repeated pagination signals into evidence-backed series reviews."""
    rows = list(
        db.execute(
            select(Url, UrlSnapshot)
            .join(UrlSnapshot, UrlSnapshot.url_id == Url.id)
            .where(
                Url.website_id == website_id,
                UrlSnapshot.crawl_run_id == crawl_run_id,
            )
            .order_by(Url.normalized_url)
        )
    )
    grouped: dict[str, list[tuple[Url, UrlSnapshot, int]]] = defaultdict(list)
    for url, snapshot in rows:
        parsed = _pagination_pattern(url.normalized_url)
        if parsed is not None:
            pattern, page_number = parsed
            grouped[pattern].append((url, snapshot, page_number))

    candidate_groups = {
        pattern: items for pattern, items in grouped.items() if len(items) >= 3
    }
    url_ids = {url.id for items in candidate_groups.values() for url, _snapshot, _page in items}
    issue_counts: dict[object, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    if url_ids:
        for issue in db.scalars(
            select(Issue).where(
                Issue.website_id == website_id,
                Issue.url_id.in_(url_ids),
                Issue.issue_type.in_(PAGINATION_CHILD_ISSUE_TYPES),
                Issue.status.in_(ACTIVE_STATUSES),
            )
        ):
            issue_counts[issue.url_id][issue.issue_type] += 1

    patterns: list[dict[str, object]] = []
    affected_urls: set[str] = set()
    for pattern, items in sorted(candidate_groups.items()):
        counts = {
            issue_type: sum(issue_counts[url.id].get(issue_type, 0) for url, _snapshot, _ in items)
            for issue_type in sorted(PAGINATION_CHILD_ISSUE_TYPES)
        }
        error_pages = [
            url.normalized_url for url, snapshot, _ in items if snapshot.status_code == 404
        ]
        if not any(counts.values()) and not error_pages:
            continue
        urls = [url.normalized_url for url, _snapshot, _ in items]
        affected_urls.update(urls)
        valid_numbers = sorted(
            page for _url, snapshot, page in items if snapshot.status_code == 200
        )
        patterns.append(
            {
                "pattern": pattern,
                "page_count": len(items),
                "valid_page_count": len(valid_numbers),
                "valid_page_range": [valid_numbers[0], valid_numbers[-1]] if valid_numbers else [],
                "error_page_count": len(error_pages),
                "error_pages": error_pages,
                "signal_counts": counts,
                "urls": urls,
            }
        )

    signals: list[IssueSignal] = []
    if patterns:
        error_count = sum(int(pattern["error_page_count"]) for pattern in patterns)
        series_label = "reeks" if len(patterns) == 1 else "reeksen"
        signals.append(
            IssueSignal(
                issue_type=PAGINATION_SERIES_ISSUE_TYPE,
                category="indexation",
                severity="medium" if error_count else "low",
                confidence="high",
                title=(
                    f"{len(affected_urls)} paginerings-URL's vormen {len(patterns)} "
                    f"herkenbare {series_label}"
                ),
                description=(
                    "Terugkerende metadata-, canonical- en dieptesignalen horen bij dezelfde "
                    "pagineringsreeksen. Ze worden daarom als templatecontrole getoond in plaats "
                    "van als losse taak per pagina."
                ),
                recommended_action=(
                    "Controleer per reeks één keer het pagineringstemplate: laat geldige pagina's "
                    "indexeerbaar en self-canonical, voorkom links naar pagina 0 en voorbij de "
                    "laatste gevulde pagina, en bepaal bewust of title en description per pagina "
                    "moeten verschillen. Bevestig de grens met een nieuwe volledige crawl."
                ),
                evidence={
                    "affected_url_count": len(affected_urls),
                    "series_count": len(patterns),
                    "error_page_count": error_count,
                    "patterns": patterns,
                    "likely_scope": "pagineringscomponent of overzichtstemplate",
                    "likely_cause": (
                        "Dezelfde pagineringscomponent herhaalt metadata en genereert links tot "
                        "of voorbij de gemeten reeksgrens."
                    ),
                    "alternative_explanation": (
                        "Gelijke metadata of een afwijkende canonical kan per reeks bewust zijn; "
                        "beoordeel daarom het template en de indexatiestrategie gezamenlijk."
                    ),
                    "verification": (
                        "alle geldige pagina's blijven 200 en de reeks genereert geen lege "
                        "grenspagina's"
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
        checked_issue_types={PAGINATION_SERIES_ISSUE_TYPE},
    )


def _pagination_pattern(value: str) -> tuple[str, int] | None:
    split = urlsplit(value)
    query = parse_qsl(split.query, keep_blank_values=True)
    pagination = [
        (name, raw_value)
        for name, raw_value in query
        if name.lower() in PAGINATION_PARAMETERS and raw_value.isdigit()
    ]
    if len(pagination) != 1:
        return None
    page_name, raw_page = pagination[0]
    rendered_query = "&".join(
        f"{name}=*" if name == page_name and item_value == raw_page else f"{name}={item_value}"
        for name, item_value in query
    )
    pattern = f"{split.scheme}://{split.netloc}{split.path}?{rendered_query}"
    return pattern, int(raw_page)

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import Url, UrlSource
from app.models.integrations import GoogleAnalyticsMetric, SearchConsoleMetric
from app.models.issues import Issue
from app.services.issue_engine import reconcile_issues
from app.services.technical_checks import IssueSignal
from app.services.url_normalization import InvalidUrlError, normalize_url

SITEMAP_ISSUE_TYPES = {"sitemap_redirect"}


def analyze_indexation_consistency(
    db: Session, *, website_id: object, crawl_run_id: object
) -> list[Issue]:
    """Add sitemap and performance context to indexation issues."""
    run = db.get(CrawlRun, crawl_run_id)
    if run is None:
        raise ValueError("Crawl run does not exist")
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
    current_sitemap_ids = set(
        db.scalars(
            select(UrlSource.url_id).where(
                UrlSource.source_type == "sitemap",
                UrlSource.last_seen_at >= run.started_at,
            )
        )
    )
    important_ids = _important_url_ids(db, website_id=website_id)
    touched: list[Issue] = []

    for url, snapshot in rows:
        in_sitemap = url.id in current_sitemap_ids
        is_important = url.is_important or url.id in important_ids
        signals: list[IssueSignal] = []
        if in_sitemap and snapshot.redirect_chain:
            signals.append(
                IssueSignal(
                    issue_type="sitemap_redirect",
                    category="indexation",
                    severity="medium",
                    title="Sitemap-URL stuurt door",
                    description=(
                        "Deze URL staat in de actuele XML-sitemap maar stuurt door naar "
                        "een andere URL."
                    ),
                    recommended_action=(
                        "Vervang de URL in de sitemap door de definitieve, indexeerbare eind-URL."
                    ),
                    evidence={
                        "in_current_sitemap": True,
                        "redirect_chain": snapshot.redirect_chain,
                        "final_url": snapshot.final_url,
                    },
                )
            )
        if snapshot.status_code == 200 and snapshot.is_indexable is False and (
            in_sitemap or is_important
        ):
            context = "de actuele sitemap" if in_sitemap else "historische GSC/GA4-prestaties"
            signals.append(
                IssueSignal(
                    issue_type="unexpected_noindex",
                    category="indexation",
                    severity="high",
                    title="Belangrijke pagina is niet indexeerbaar",
                    description=(
                        f"De pagina heeft een noindex-instructie, maar is belangrijk op basis van "
                        f"{context}."
                    ),
                    recommended_action=(
                        "Verwijder de noindex wanneer deze pagina organisch vindbaar moet zijn; "
                        "verwijder hem anders uit de sitemap en interne promotie."
                    ),
                    evidence={
                        "in_current_sitemap": in_sitemap,
                        "has_recent_organic_value": is_important,
                        "status_code": snapshot.status_code,
                    },
                )
            )
        if in_sitemap and _canonical_points_elsewhere(snapshot):
            signals.append(
                IssueSignal(
                    issue_type="canonical_other_url",
                    category="indexation",
                    severity="medium",
                    title="Sitemap-URL canonicaliseert naar een andere URL",
                    description=(
                        "De actuele sitemap noemt deze URL als primaire pagina, terwijl de "
                        "canonical een andere URL aanwijst."
                    ),
                    recommended_action=(
                        "Laat de sitemap alleen de canonical eind-URL bevatten of corrigeer "
                        "een onbedoeld afwijkende canonical."
                    ),
                    evidence={
                        "in_current_sitemap": True,
                        "canonical": snapshot.canonical,
                        "page_url": snapshot.final_url or snapshot.requested_url,
                    },
                )
            )
        touched.extend(
            reconcile_issues(
                db,
                website_id=website_id,
                url_id=url.id,
                crawl_run_id=crawl_run_id,
                snapshot_id=snapshot.id,
                signals=signals,
                checked_issue_types=SITEMAP_ISSUE_TYPES,
            )
        )
    db.commit()
    return touched


def _canonical_points_elsewhere(snapshot: UrlSnapshot) -> bool:
    if not snapshot.canonical:
        return False
    page_url = snapshot.final_url or snapshot.requested_url
    try:
        return normalize_url(snapshot.canonical) != normalize_url(page_url)
    except InvalidUrlError:
        return True


def _important_url_ids(db: Session, *, website_id: object) -> set[object]:
    since = date.today() - timedelta(days=90)
    result: set[object] = set()
    search_rows = db.execute(
        select(
            SearchConsoleMetric.url_id,
            func.sum(SearchConsoleMetric.clicks),
            func.sum(SearchConsoleMetric.impressions),
        )
        .where(
            SearchConsoleMetric.website_id == website_id,
            SearchConsoleMetric.date >= since,
            SearchConsoleMetric.url_id.is_not(None),
        )
        .group_by(SearchConsoleMetric.url_id)
    )
    for url_id, clicks, impressions in search_rows:
        if float(clicks or 0) >= 10 or int(impressions or 0) >= 1000:
            result.add(url_id)
    analytics_rows = db.execute(
        select(
            GoogleAnalyticsMetric.url_id,
            func.sum(GoogleAnalyticsMetric.sessions),
            func.sum(GoogleAnalyticsMetric.key_events),
        )
        .where(
            GoogleAnalyticsMetric.website_id == website_id,
            GoogleAnalyticsMetric.date >= since,
            GoogleAnalyticsMetric.url_id.is_not(None),
        )
        .group_by(GoogleAnalyticsMetric.url_id)
    )
    for url_id, sessions, key_events in analytics_rows:
        if int(sessions or 0) >= 100 or float(key_events or 0) >= 1:
            result.add(url_id)
    return result

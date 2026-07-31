from collections.abc import Callable
from datetime import date, timedelta

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session, aliased

from app.models.common import utc_now
from app.models.crawl import UrlLink, UrlSnapshot
from app.models.discovery import Url, UrlSource
from app.models.integrations import GoogleAnalyticsMetric, SearchConsoleMetric
from app.models.issues import Issue
from app.services.discovery_pages import discovery_only_url_ids
from app.services.element_locations import mark_target_elements_for_targets
from app.services.issue_engine import reconcile_issues
from app.services.link_filtering import is_non_navigational_link_target
from app.services.technical_checks import IssueSignal
from app.services.url_filtering import is_probable_html_page
from app.services.url_normalization import InvalidUrlError, normalize_url

INTERNAL_LINK_ISSUE_TYPES = {
    "deep_page",
    "important_page_few_internal_links",
    "internally_linked_redirect",
}
SOURCE_REDIRECT_ISSUE_TYPE = "multiple_redirected_internal_links"
GENERIC_ANCHOR_ISSUE_TYPE = "generic_internal_anchor_text"
GENERIC_ANCHOR_TEXTS = {
    "bekijk",
    "click here",
    "klik hier",
    "learn more",
    "lees meer",
    "meer",
    "more",
    "read more",
}
MAX_RECOMMENDED_CRAWL_DEPTH = 3
VERY_DEEP_CRAWL_DEPTH = 6
MAX_WEAK_INBOUND_LINKS = 1


def detect_orphan_pages(db: Session, *, website_id: object, crawl_run_id: object) -> list[Url]:
    discovery_only_ids = discovery_only_url_ids(
        db,
        website_id=website_id,
        crawl_run_id=crawl_run_id,
    )
    orphan_urls = list(
        db.scalars(
            select(Url)
            .join(UrlSource, UrlSource.url_id == Url.id)
            .where(
                Url.website_id == website_id,
                Url.is_active.is_(True),
                Url.current_status_code == 200,
                Url.is_indexable.is_(True),
                Url.crawl_depth.is_(None),
                UrlSource.source_type == "sitemap",
            )
            .distinct()
            .order_by(Url.normalized_url)
        )
    )
    orphan_urls = [url for url in orphan_urls if url.id not in discovery_only_ids]
    for url in orphan_urls:
        reconcile_issues(
            db,
            website_id=website_id,
            url_id=url.id,
            crawl_run_id=crawl_run_id,
            snapshot_id=None,
            signals=[
                IssueSignal(
                    issue_type="orphan_page",
                    category="internal_links",
                    severity="medium",
                    title="Indexeerbare pagina staat buiten de interne sitestructuur",
                    description=(
                        "De URL staat in de sitemap en is indexeerbaar, maar de volledige crawl "
                        "vond geen interne route naar deze pagina. Dit bewijst nog niet of de "
                        "pagina moet blijven bestaan."
                    ),
                    recommended_action=(
                        "Bepaal eerst of de pagina zelfstandig moet blijven. Geef haar daarna een "
                        "logische plek in de sitestructuur, of voeg haar samen of redirect haar "
                        "naar de bedoelde bestemming en werk de sitemap bij."
                    ),
                    evidence={
                        "url": url.normalized_url,
                        "crawl_depth": None,
                        "structure_status": "outside_internal_structure",
                        "decision_required": True,
                    },
                )
            ],
            checked_issue_types={"orphan_page"},
        )
    orphan_ids = {url.id for url in orphan_urls}
    existing = list(
        db.scalars(
            select(Issue).where(
                Issue.website_id == website_id,
                Issue.issue_type == "orphan_page",
                Issue.status.not_in(["resolved", "verified", "ignored", "accepted_risk"]),
            )
        )
    )
    for issue in existing:
        if issue.url_id not in orphan_ids:
            issue.status = "resolved"
            issue.resolved_at = utc_now()
    return orphan_urls


def analyze_internal_link_quality(
    db: Session,
    *,
    website_id: object,
    crawl_run_id: object,
    check_control: Callable[[], None] | None = None,
) -> list[Issue]:
    """Detect actionable internal-link problems after a complete site crawl."""
    urls = list(
        db.scalars(
            select(Url)
            .join(UrlSnapshot, UrlSnapshot.url_id == Url.id)
            .where(
                Url.website_id == website_id,
                UrlSnapshot.crawl_run_id == crawl_run_id,
            )
            .distinct()
            .order_by(Url.normalized_url)
        )
    )
    discovery_only_ids = discovery_only_url_ids(
        db,
        website_id=website_id,
        crawl_run_id=crawl_run_id,
    )
    inbound_counts = _inbound_link_counts(db, crawl_run_id=crawl_run_id)
    inbound_sources = _inbound_link_sources(db, crawl_run_id=crawl_run_id)
    important_urls = _important_url_ids(db, website_id=website_id)
    touched: list[Issue] = []
    redirect_target_urls = {
        url.normalized_url
        for url in urls
        if _is_internally_linked_redirect(url, inbound_counts.get(url.id, 0))
    }
    mark_target_elements_for_targets(
        db,
        crawl_run_id=crawl_run_id,
        target_urls=redirect_target_urls,
        issue_type="internally_linked_redirect",
        element_types={"a", "button"},
        check_control=check_control,
    )

    for url in urls:
        _check_control(check_control)
        signals: list[IssueSignal] = []
        if url.id in discovery_only_ids:
            touched.extend(
                reconcile_issues(
                    db,
                    website_id=website_id,
                    url_id=url.id,
                    crawl_run_id=crawl_run_id,
                    snapshot_id=None,
                    signals=[],
                    checked_issue_types=INTERNAL_LINK_ISSUE_TYPES,
                )
            )
            continue
        inbound_count = inbound_counts.get(url.id, 0)
        if _is_internally_linked_redirect(url, inbound_count):
            signals.append(
                IssueSignal(
                    issue_type="internally_linked_redirect",
                    category="internal_links",
                    severity="medium",
                    title="Interne links wijzen naar een redirect",
                    description=(
                        f"Deze URL ontvangt links vanaf {inbound_count} interne pagina's en "
                        "stuurt bezoekers en crawlers door."
                    ),
                    recommended_action=(
                        "Werk de interne links bij zodat ze rechtstreeks naar de eind-URL wijzen."
                    ),
                    evidence={
                        "incoming_internal_pages": inbound_count,
                        "source_urls": inbound_sources.get(url.id, [])[:20],
                        "redirect_url": url.normalized_url,
                        "final_url": url.current_final_url,
                    },
                )
            )
        deep_page_reason = _deep_page_reason(
            url,
            inbound_count=inbound_count,
            is_important=url.id in important_urls,
        )
        if deep_page_reason is not None:
            signals.append(
                IssueSignal(
                    issue_type="deep_page",
                    category="internal_links",
                    severity="low",
                    title="Pagina ligt diep in de sitestructuur",
                    description=(
                        f"De pagina is pas na {url.crawl_depth} interne stappen bereikbaar en "
                        f"is relevant om te beoordelen omdat {deep_page_reason}."
                    ),
                    recommended_action=(
                        "Beoordeel of de pagina dichter bij een relevante categorie, hub of "
                        "navigatieroute hoort. Voeg alleen een extra link toe wanneer dat de "
                        "gebruikersroute werkelijk verbetert."
                    ),
                    evidence={
                        "crawl_depth": url.crawl_depth,
                        "recommended_maximum": MAX_RECOMMENDED_CRAWL_DEPTH,
                        "incoming_internal_pages": inbound_count,
                        "is_important": url.id in important_urls,
                        "review_reason": deep_page_reason,
                    },
                )
            )
        if (
            _is_indexable_html_page(url)
            and url.id in important_urls
            and inbound_count <= MAX_WEAK_INBOUND_LINKS
        ):
            signals.append(
                IssueSignal(
                    issue_type="important_page_few_internal_links",
                    category="internal_links",
                    severity="medium",
                    title="Belangrijke pagina krijgt weinig interne links",
                    description=(
                        f"Deze organisch belangrijke pagina ontvangt links vanaf slechts "
                        f"{inbound_count} interne pagina's."
                    ),
                    recommended_action=(
                        "Voeg contextuele interne links toe vanaf relevante pagina's "
                        "met autoriteit."
                    ),
                    evidence={
                        "incoming_internal_pages": inbound_count,
                        "importance_basis": (
                            "GSC/GA4 in de laatste 28 dagen of handmatig belangrijk"
                        ),
                        "source_urls": inbound_sources.get(url.id, [])[:20],
                    },
                )
            )
        touched.extend(
            reconcile_issues(
                db,
                website_id=website_id,
                url_id=url.id,
                crawl_run_id=crawl_run_id,
                snapshot_id=None,
                signals=signals,
                checked_issue_types=INTERNAL_LINK_ISSUE_TYPES,
            )
        )
    touched.extend(
        analyze_redirect_source_groups(
            db,
            website_id=website_id,
            crawl_run_id=crawl_run_id,
        )
    )
    touched.extend(
        analyze_generic_anchor_text(
            db,
            website_id=website_id,
            crawl_run_id=crawl_run_id,
        )
    )
    db.commit()
    return touched


def _check_control(check_control: Callable[[], None] | None) -> None:
    if check_control is not None:
        check_control()


def analyze_redirect_source_groups(
    db: Session, *, website_id: object, crawl_run_id: object
) -> list[Issue]:
    """Group multiple redirect links by the source page where they can be fixed together."""
    redirects_by_source = _redirect_links_by_source(db, crawl_run_id=crawl_run_id)
    discovery_only_ids = discovery_only_url_ids(
        db,
        website_id=website_id,
        crawl_run_id=crawl_run_id,
    )
    source_ids = set(redirects_by_source)
    source_ids.update(
        db.scalars(
            select(Issue.url_id).where(
                Issue.website_id == website_id,
                Issue.issue_type == SOURCE_REDIRECT_ISSUE_TYPE,
                Issue.url_id.is_not(None),
            )
        )
    )
    touched: list[Issue] = []
    for source_id in source_ids:
        redirected_links = redirects_by_source.get(source_id, [])
        signals: list[IssueSignal] = []
        if source_id not in discovery_only_ids and len(redirected_links) >= 2:
            signals.append(
                IssueSignal(
                    issue_type=SOURCE_REDIRECT_ISSUE_TYPE,
                    category="internal_links",
                    severity="medium",
                    title=f"{len(redirected_links)} interne links gaan via een redirect",
                    description=(
                        "Deze bronpagina linkt naar meerdere oude URL's die eerst doorsturen. "
                        "De links kunnen gezamenlijk op deze pagina of in het gedeelde "
                        "contentblok worden bijgewerkt."
                    ),
                    recommended_action=(
                        "Vervang op deze bronpagina iedere redirect-URL door de opgeslagen "
                        "eind-URL. Controleer daarna dat alle links rechtstreeks een 200-status "
                        "geven en dat ankerteksten inhoudelijk blijven passen."
                    ),
                    evidence={
                        "redirected_link_count": len(redirected_links),
                        "redirected_links": redirected_links,
                        "likely_scope": "bronpagina of gedeeld contentblok",
                        "verification": (
                            "geen interne link op deze pagina gaat nog via een redirect"
                        ),
                    },
                    confidence="high",
                )
            )
        touched.extend(
            reconcile_issues(
                db,
                website_id=website_id,
                url_id=source_id,
                crawl_run_id=crawl_run_id,
                snapshot_id=None,
                signals=signals,
                checked_issue_types={SOURCE_REDIRECT_ISSUE_TYPE},
            )
        )
    return touched


def analyze_generic_anchor_text(
    db: Session, *, website_id: object, crawl_run_id: object
) -> list[Issue]:
    """Create one site-level quality action for non-descriptive internal anchors."""
    target = aliased(Url)
    rows = list(
        db.execute(
            select(
                Url.normalized_url,
                UrlLink.target_url,
                UrlLink.anchor_text,
                target.current_status_code,
            )
            .join(Url, Url.id == UrlLink.source_url_id)
            .outerjoin(target, target.id == UrlLink.target_url_id)
            .where(
                Url.website_id == website_id,
                UrlLink.crawl_run_id == crawl_run_id,
                UrlLink.is_internal.is_(True),
            )
            .order_by(Url.normalized_url, UrlLink.target_url)
        )
    )
    generic_links: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for source_url, target_url, anchor_text, status_code in rows:
        normalized_anchor = " ".join((anchor_text or "").casefold().split()).strip(" .:;,-–—→")
        key = (source_url, target_url, normalized_anchor)
        if (
            normalized_anchor not in GENERIC_ANCHOR_TEXTS
            or is_non_navigational_link_target(target_url)
            or key in seen
        ):
            continue
        seen.add(key)
        generic_links.append(
            {
                "source_url": source_url,
                "target_url": target_url,
                "anchor_text": anchor_text,
                "status_code": status_code,
                "target_is_broken": status_code in {404, 410},
            }
        )
    source_urls = sorted({str(link["source_url"]) for link in generic_links})
    broken_count = sum(bool(link["target_is_broken"]) for link in generic_links)
    signals: list[IssueSignal] = []
    if generic_links:
        signals.append(
            IssueSignal(
                issue_type=GENERIC_ANCHOR_ISSUE_TYPE,
                category="internal_links",
                severity="low",
                confidence="high",
                title=(
                    f"Niet-beschrijvende interne linkteksten op {len(source_urls)} "
                    f"pagina{'s' if len(source_urls) != 1 else ''}"
                ),
                description=(
                    "Generieke linkteksten zoals 'lees meer' beschrijven de bestemming niet. "
                    "Dat geeft zoekmachines en gebruikers van hulptechnologie minder context."
                ),
                recommended_action=(
                    "Vervang iedere generieke linktekst door een korte beschrijving van de "
                    "bestemmingspagina. Herstel bij gemarkeerde dode links tegelijk de "
                    "bestemming."
                ),
                evidence={
                    "affected_source_pages": len(source_urls),
                    "generic_link_count": len(generic_links),
                    "broken_link_count": broken_count,
                    "source_urls": source_urls[:200],
                    "generic_links": generic_links[:500],
                    "verification": (
                        "alle interne links hebben een beschrijvende tekst en bereiken een "
                        "werkende bestemming"
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
        checked_issue_types={GENERIC_ANCHOR_ISSUE_TYPE},
    )


def _inbound_link_counts(db: Session, *, crawl_run_id: object) -> dict[object, int]:
    rows = db.execute(
        select(UrlLink.target_url_id, func.count(distinct(UrlLink.source_url_id)))
        .where(
            UrlLink.crawl_run_id == crawl_run_id,
            UrlLink.is_internal.is_(True),
            UrlLink.target_url_id.is_not(None),
        )
        .group_by(UrlLink.target_url_id)
    )
    return {url_id: int(count) for url_id, count in rows}


def _inbound_link_sources(db: Session, *, crawl_run_id: object) -> dict[object, list[str]]:
    rows = db.execute(
        select(UrlLink.target_url_id, Url.normalized_url)
        .join(Url, Url.id == UrlLink.source_url_id)
        .where(
            UrlLink.crawl_run_id == crawl_run_id,
            UrlLink.is_internal.is_(True),
            UrlLink.target_url_id.is_not(None),
        )
        .distinct()
        .order_by(UrlLink.target_url_id, Url.normalized_url)
    )
    result: dict[object, list[str]] = {}
    for target_url_id, source_url in rows:
        result.setdefault(target_url_id, []).append(source_url)
    return result


def _redirect_links_by_source(
    db: Session, *, crawl_run_id: object
) -> dict[object, list[dict[str, object]]]:
    rows = db.execute(
        select(
            UrlLink.source_url_id,
            UrlLink.target_url,
            UrlLink.anchor_text,
            Url.current_final_url,
            Url.current_status_code,
        )
        .join(Url, Url.id == UrlLink.target_url_id)
        .where(
            UrlLink.crawl_run_id == crawl_run_id,
            UrlLink.is_internal.is_(True),
            UrlLink.source_url_id != UrlLink.target_url_id,
            Url.current_final_url.is_not(None),
        )
        .order_by(UrlLink.source_url_id, UrlLink.target_url, UrlLink.anchor_text)
    )
    result: dict[object, list[dict[str, object]]] = {}
    seen: set[tuple[object, str, str]] = set()
    for source_id, target_url, anchor_text, final_url, status_code in rows:
        if is_non_navigational_link_target(target_url):
            continue
        try:
            is_redirect = normalize_url(target_url) != normalize_url(final_url)
        except InvalidUrlError:
            is_redirect = False
        key = (source_id, target_url, anchor_text or "")
        if not is_redirect or key in seen:
            continue
        seen.add(key)
        result.setdefault(source_id, []).append(
            {
                "redirect_url": target_url,
                "final_url": final_url,
                "anchor_text": anchor_text or "(geen ankertekst)",
                "status_code": status_code,
            }
        )
    return result


def _important_url_ids(db: Session, *, website_id: object) -> set[object]:
    since = date.today() - timedelta(days=28)
    result = set(
        db.scalars(
            select(Url.id).where(
                Url.website_id == website_id,
                Url.is_important.is_(True),
            )
        )
    )
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


def _is_indexable_html_page(url: Url) -> bool:
    return (
        url.is_active
        and url.current_status_code == 200
        and url.is_indexable is True
        and is_probable_html_page(url.normalized_url)
    )


def _deep_page_reason(url: Url, *, inbound_count: int, is_important: bool) -> str | None:
    if not _is_indexable_html_page(url):
        return None
    depth = url.crawl_depth or 0
    if depth <= MAX_RECOMMENDED_CRAWL_DEPTH:
        return None
    if is_important:
        return "de pagina organisch of handmatig belangrijk is"
    if depth >= VERY_DEEP_CRAWL_DEPTH:
        return f"de crawldiepte {depth} uitzonderlijk hoog is"
    if inbound_count <= MAX_WEAK_INBOUND_LINKS:
        return f"slechts {inbound_count} interne bronpagina's naar de pagina linken"
    return None


def _is_internally_linked_redirect(url: Url, inbound_count: int) -> bool:
    if (
        not url.is_active
        or inbound_count == 0
        or not url.current_final_url
        or is_non_navigational_link_target(url.normalized_url)
    ):
        return False
    try:
        return normalize_url(url.current_final_url) != normalize_url(url.normalized_url)
    except InvalidUrlError:
        return False

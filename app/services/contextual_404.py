import re
from collections import defaultdict
from urllib.parse import parse_qsl, urlsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.crawl import UrlLink
from app.models.discovery import Url, UrlSource
from app.models.issues import Issue
from app.services.element_locations import mark_target_elements
from app.services.issue_engine import reconcile_issues
from app.services.technical_checks import IssueSignal

CONTEXTUAL_404_TYPES = {"http_404", "internally_linked_404", "sitemap_404"}
SOURCE_PAGE_404_TYPE = "multiple_broken_internal_links"
PATTERNED_404_TYPE = "patterned_404_urls"
PAGINATION_PARAMETERS = {"page", "paged", "p", "offset", "start"}
PATH_PAGE_RE = re.compile(r"(?:/page/\d+|/page-\d+)(?:/)?$", re.IGNORECASE)


def classify_404_issues(db: Session, *, website_id: object, crawl_run_id: object) -> None:
    urls = list(
        db.scalars(
            select(Url).where(
                Url.website_id == website_id,
                Url.is_active.is_(True),
                Url.current_status_code == 404,
            )
        )
    )
    for url in urls:
        incoming_links = (
            db.scalar(
                select(func.count(UrlLink.id)).where(
                    UrlLink.crawl_run_id == crawl_run_id,
                    UrlLink.target_url_id == url.id,
                    UrlLink.source_url_id != url.id,
                    UrlLink.is_internal.is_(True),
                )
            )
            or 0
        )
        in_sitemap = db.scalar(
            select(UrlSource.id).where(
                UrlSource.url_id == url.id,
                UrlSource.source_type == "sitemap",
            )
        )
        signal = _signal(incoming_links=incoming_links, in_sitemap=in_sitemap is not None)
        if incoming_links:
            mark_target_elements(
                db,
                crawl_run_id=crawl_run_id,
                target_url=url.normalized_url,
                issue_type="internally_linked_404",
                element_types={"a", "button"},
            )
        reconcile_issues(
            db,
            website_id=website_id,
            url_id=url.id,
            crawl_run_id=crawl_run_id,
            snapshot_id=None,
            signals=[signal],
            checked_issue_types=CONTEXTUAL_404_TYPES,
        )
    _classify_url_patterns(
        db,
        website_id=website_id,
        crawl_run_id=crawl_run_id,
        urls=[url.normalized_url for url in urls],
    )
    _classify_source_pages(db, website_id=website_id, crawl_run_id=crawl_run_id)
    db.commit()


def _classify_url_patterns(
    db: Session,
    *,
    website_id: object,
    crawl_run_id: object,
    urls: list[str],
) -> None:
    candidates: dict[tuple[str, str], set[str]] = defaultdict(set)
    for url in urls:
        split = urlsplit(url)
        query = parse_qsl(split.query, keep_blank_values=True)
        pagination_names = sorted(
            {
                name.lower()
                for name, value in query
                if name.lower() in PAGINATION_PARAMETERS and value
            }
        )
        if pagination_names:
            key = f"{split.path}?{'&'.join(f'{name}=*' for name in pagination_names)}"
            candidates[("pagination", key)].add(url)
            continue
        if query:
            names = sorted({name.lower() for name, _value in query})
            key = f"{split.path}?{'&'.join(f'{name}=*' for name in names)}"
            candidates[("parameter", key)].add(url)
            continue
        if PATH_PAGE_RE.search(split.path):
            key = PATH_PAGE_RE.sub("/page/*", split.path)
            candidates[("pagination", key)].add(url)

    patterns: list[dict[str, object]] = []
    for (pattern_type, pattern), grouped_urls in sorted(candidates.items()):
        minimum_size = 2 if pattern_type == "pagination" else 3
        if len(grouped_urls) < minimum_size:
            continue
        patterns.append(
            {
                "pattern_type": pattern_type,
                "pattern": pattern,
                "url_count": len(grouped_urls),
                "urls": sorted(grouped_urls),
            }
        )

    signals: list[IssueSignal] = []
    if patterns:
        affected_urls = {url for pattern in patterns for url in pattern["urls"]}
        pagination_count = sum(
            1 for pattern in patterns if pattern["pattern_type"] == "pagination"
        )
        likely_cause = (
            "De site genereert waarschijnlijk pagineringslinks naar niet-bestaande pagina's."
            if pagination_count
            else "De site genereert waarschijnlijk parameter- of filter-URL's die niet bestaan."
        )
        signals.append(
            IssueSignal(
                issue_type=PATTERNED_404_TYPE,
                category="internal_links",
                severity="high",
                confidence="high" if pagination_count else "medium",
                title=(
                    f"{len(affected_urls)} 404-URL's vormen {len(patterns)} herkenbaar patroon"
                    + ("" if len(patterns) == 1 else "en")
                ),
                description=(
                    f"{likely_cause} De losse 404's zijn daarom waarschijnlijk symptomen van "
                    "dezelfde navigatie-, filter- of templateconfiguratie."
                ),
                recommended_action=(
                    "Controleer waar deze URL-reeks wordt opgebouwd. Begrens paginering bij de "
                    "laatste bestaande pagina, verwijder links naar lege resultaten en controleer "
                    "canonical- en robotsregels voor geldige varianten. Bevestig met een nieuwe "
                    "crawl dat geen URL uit het patroon nog intern wordt gegenereerd als 404."
                ),
                evidence={
                    "affected_url_count": len(affected_urls),
                    "pattern_count": len(patterns),
                    "patterns": patterns,
                    "likely_cause": likely_cause,
                    "alternative_explanation": (
                        "Verouderde handmatige links kunnen hetzelfde patroon nabootsen; "
                        "controleer daarom eerst de bronpagina's en het pagineringstemplate."
                    ),
                    "verification": "geen intern ontdekte URL uit deze patronen geeft nog een 404",
                },
            )
        )
    reconcile_issues(
        db,
        website_id=website_id,
        url_id=None,
        crawl_run_id=crawl_run_id,
        snapshot_id=None,
        signals=signals,
        checked_issue_types={PATTERNED_404_TYPE},
    )


def _classify_source_pages(db: Session, *, website_id: object, crawl_run_id: object) -> None:
    rows = db.execute(
        select(
            UrlLink.source_url_id,
            UrlLink.target_url,
            UrlLink.anchor_text,
            Url.current_status_code,
        )
        .join(Url, Url.id == UrlLink.target_url_id)
        .where(
            UrlLink.crawl_run_id == crawl_run_id,
            UrlLink.is_internal.is_(True),
            UrlLink.source_url_id != UrlLink.target_url_id,
            Url.current_status_code == 404,
        )
        .order_by(UrlLink.source_url_id, UrlLink.target_url, UrlLink.anchor_text)
    )
    broken_by_source: dict[object, list[dict[str, object]]] = {}
    seen: set[tuple[object, str, str]] = set()
    for source_id, target_url, anchor_text, status_code in rows:
        key = (source_id, target_url, anchor_text or "")
        if key in seen:
            continue
        seen.add(key)
        broken_by_source.setdefault(source_id, []).append(
            {
                "target_url": target_url,
                "anchor_text": anchor_text or "(geen ankertekst)",
                "status_code": status_code,
            }
        )

    source_ids = set(
        db.scalars(
            select(UrlLink.source_url_id).where(UrlLink.crawl_run_id == crawl_run_id).distinct()
        )
    )
    source_ids.update(
        db.scalars(
            select(Issue.url_id).where(
                Issue.website_id == website_id,
                Issue.issue_type == SOURCE_PAGE_404_TYPE,
                Issue.url_id.is_not(None),
            )
        )
    )
    for source_id in source_ids:
        broken_links = broken_by_source.get(source_id, [])
        signals: list[IssueSignal] = []
        if len(broken_links) >= 2:
            count = len(broken_links)
            signals.append(
                IssueSignal(
                    issue_type=SOURCE_PAGE_404_TYPE,
                    category="internal_links",
                    severity="high",
                    title=f"{count} dode interne links op deze pagina",
                    description=(
                        f"Deze pagina bevat {count} verschillende interne links naar pagina's "
                        "die niet meer bestaan. Dit belemmert bezoekers en zoekmachines binnen "
                        "dezelfde gebruikersroute."
                    ),
                    recommended_action=(
                        "Werk de onderstaande links op deze bronpagina gezamenlijk bij. Vervang "
                        "ieder doel door de meest relevante bestaande pagina of verwijder de "
                        "link wanneer geen passende bestemming bestaat. Controleer daarna dat "
                        "alle doelen rechtstreeks een 200-status geven."
                    ),
                    evidence={
                        "broken_link_count": count,
                        "broken_links": broken_links,
                        "likely_scope": "bronpagina of gedeeld contentblok",
                        "verification": "geen interne link op deze pagina geeft nog een 404",
                    },
                    confidence="high",
                )
            )
        reconcile_issues(
            db,
            website_id=website_id,
            url_id=source_id,
            crawl_run_id=crawl_run_id,
            snapshot_id=None,
            signals=signals,
            checked_issue_types={SOURCE_PAGE_404_TYPE},
        )


def _signal(*, incoming_links: int, in_sitemap: bool) -> IssueSignal:
    if incoming_links:
        return IssueSignal(
            issue_type="internally_linked_404",
            category="internal_links",
            severity="high",
            title="Interne links wijzen naar een 404",
            description=f"De 404-URL ontvangt {incoming_links} interne links.",
            recommended_action="Herstel de interne links of stel een relevante redirect in.",
            evidence={"incoming_internal_links": incoming_links},
        )
    if in_sitemap:
        return IssueSignal(
            issue_type="sitemap_404",
            category="indexation",
            severity="medium",
            title="404-URL staat in de sitemap",
            description="De URL staat in de XML-sitemap maar geeft een 404.",
            recommended_action="Verwijder de URL uit de sitemap of herstel de pagina.",
            evidence={"in_sitemap": True},
        )
    return IssueSignal(
        issue_type="http_404",
        category="reachability",
        severity="high",
        title="Pagina geeft 404",
        description="De bekende URL geeft een 404.",
        recommended_action="Herstel de pagina of stel een relevante redirect in.",
        evidence={"status_code": 404},
    )

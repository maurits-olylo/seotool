import math
from urllib.parse import urljoin, urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crawl import UrlSnapshot
from app.models.discovery import Url
from app.models.issues import Issue
from app.services.issue_engine import reconcile_issues
from app.services.technical_checks import IssueSignal
from app.services.url_filtering import is_probable_html_page
from app.services.url_normalization import InvalidUrlError, normalize_url

BREADCRUMB_ISSUE_TYPES = {"missing_breadcrumb_schema"}
CONTEXTUAL_SCHEMA_ISSUE_TYPES = {
    "structured_data_required_fields_missing",
    "structured_data_visible_content_mismatch",
    "structured_data_image_unreachable",
}
CONTEXTUAL_SCHEMA_REQUIREMENTS = {
    "Product": (("name", "image"), (("offers", "review", "aggregateRating"),)),
    "Article": (("headline", "image", "datePublished"), ()),
    "BlogPosting": (("headline", "image", "datePublished"), ()),
    "NewsArticle": (("headline", "image", "datePublished"), ()),
    "Organization": (("name", "url"), ()),
    "LocalBusiness": (("name", "address"), ()),
    "Event": (("name", "startDate", "location"), ()),
    "VideoObject": (
        ("name", "description", "thumbnailUrl", "uploadDate"),
        (("contentUrl", "embedUrl"),),
    ),
}
MINIMUM_BREADCRUMB_EXAMPLES = 3
MINIMUM_BREADCRUMB_COVERAGE = 0.5


def analyze_breadcrumb_consistency(
    db: Session, *, website_id: object, crawl_run_id: object
) -> list[Issue]:
    """Report missing BreadcrumbList only when the site demonstrably uses it."""
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
    eligible_indices = [
        index for index, (url, snapshot) in enumerate(rows) if _is_deep_content_page(url, snapshot)
    ]
    with_breadcrumb = [
        index
        for index in eligible_indices
        if "BreadcrumbList" in (rows[index][1].schema_types or [])
    ]
    minimum_expected = max(
        MINIMUM_BREADCRUMB_EXAMPLES,
        math.ceil(len(eligible_indices) * MINIMUM_BREADCRUMB_COVERAGE),
    )
    site_uses_breadcrumbs = len(with_breadcrumb) >= minimum_expected
    eligible_set = set(eligible_indices)
    breadcrumb_set = set(with_breadcrumb)
    touched: list[Issue] = []

    for index, (url, snapshot) in enumerate(rows):
        signals: list[IssueSignal] = []
        if site_uses_breadcrumbs and index in eligible_set and index not in breadcrumb_set:
            signals.append(
                IssueSignal(
                    issue_type="missing_breadcrumb_schema",
                    category="structured_data",
                    severity="low",
                    confidence="high",
                    title="Breadcrumb structured data ontbreekt",
                    description=(
                        "Vergelijkbare diepe pagina's gebruiken BreadcrumbList, maar deze "
                        "indexeerbare pagina niet."
                    ),
                    recommended_action=(
                        "Voeg een BreadcrumbList toe die overeenkomt met de zichtbare "
                        "broodkruimelnavigatie."
                    ),
                    evidence={
                        "crawl_depth": url.crawl_depth,
                        "eligible_pages": len(eligible_indices),
                        "pages_with_breadcrumb_schema": len(with_breadcrumb),
                        "site_coverage_percent": round(
                            len(with_breadcrumb) / len(eligible_indices) * 100, 1
                        ),
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
                checked_issue_types=BREADCRUMB_ISSUE_TYPES,
            )
        )
    db.commit()
    return touched


def analyze_contextual_structured_data(
    db: Session, *, website_id: object, crawl_run_id: object
) -> list[Issue]:
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
    known_urls = {
        item.normalized_url: item
        for item in db.scalars(select(Url).where(Url.website_id == website_id))
    }
    touched: list[Issue] = []
    for url, snapshot in rows:
        nodes = contextual_schema_nodes(snapshot.schema_data or [])
        signals = _contextual_schema_signals(snapshot, nodes, known_urls)
        touched.extend(
            reconcile_issues(
                db,
                website_id=website_id,
                url_id=url.id,
                crawl_run_id=crawl_run_id,
                snapshot_id=snapshot.id,
                signals=signals,
                checked_issue_types=CONTEXTUAL_SCHEMA_ISSUE_TYPES,
            )
        )
    db.commit()
    return touched


def contextual_schema_nodes(values: list[object]) -> list[tuple[str, dict[str, object]]]:
    found: list[tuple[str, dict[str, object]]] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            raw_types = value.get("@type")
            types = [raw_types] if isinstance(raw_types, str) else raw_types
            if isinstance(types, list):
                for schema_type in types:
                    if (
                        isinstance(schema_type, str)
                        and schema_type in CONTEXTUAL_SCHEMA_REQUIREMENTS
                    ):
                        found.append((schema_type, value))
            graph = value.get("@graph")
            if isinstance(graph, list):
                for child in graph:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(values)
    return found


def schema_image_urls(values: list[object]) -> list[str]:
    urls: set[str] = set()
    for _schema_type, node in contextual_schema_nodes(values):
        for field in ("image", "logo", "thumbnailUrl"):
            urls.update(_schema_urls(node.get(field)))
    return sorted(urls)


def _contextual_schema_signals(
    snapshot: UrlSnapshot,
    nodes: list[tuple[str, dict[str, object]]],
    known_urls: dict[str, Url],
) -> list[IssueSignal]:
    if snapshot.status_code != 200 or not nodes:
        return []
    missing: list[dict[str, object]] = []
    mismatches: list[dict[str, str]] = []
    broken_images: list[dict[str, object]] = []
    visible = " ".join(
        [
            snapshot.title or "",
            " ".join((snapshot.headings or {}).get("h1", [])),
            snapshot.main_content or "",
        ]
    ).casefold()
    for schema_type, node in nodes:
        required, one_of_groups = CONTEXTUAL_SCHEMA_REQUIREMENTS[schema_type]
        missing_fields = [field for field in required if not _has_value(node.get(field))]
        missing_groups = [
            list(group)
            for group in one_of_groups
            if not any(_has_value(node.get(field)) for field in group)
        ]
        if missing_fields or missing_groups:
            missing.append(
                {
                    "schema_type": schema_type,
                    "missing_fields": missing_fields,
                    "missing_one_of": missing_groups,
                }
            )
        identity_field = "headline" if "headline" in node else "name"
        identity = node.get(identity_field)
        if (
            isinstance(identity, str)
            and len(identity.strip()) >= 3
            and identity.strip().casefold() not in visible
        ):
            mismatches.append(
                {
                    "schema_type": schema_type,
                    "field": identity_field,
                    "schema_value": identity.strip()[:300],
                }
            )
        for image_url in schema_image_urls([node]):
            try:
                normalized = normalize_url(
                    urljoin(snapshot.final_url or snapshot.requested_url, image_url)
                )
            except InvalidUrlError:
                continue
            known = known_urls.get(normalized)
            if known and known.current_status_code is not None and known.current_status_code >= 400:
                broken_images.append(
                    {
                        "schema_type": schema_type,
                        "url": normalized,
                        "status_code": known.current_status_code,
                    }
                )
    signals: list[IssueSignal] = []
    if missing:
        signals.append(
            IssueSignal(
                issue_type="structured_data_required_fields_missing",
                category="structured_data",
                severity="medium",
                confidence="high",
                title="Vereiste structured-data-informatie ontbreekt",
                description=(
                    "Een herkend schematype mist velden die nodig zijn voor betrouwbare "
                    "interpretatie."
                ),
                recommended_action=(
                    "Vul alleen de genoemde velden aan en laat de markup overeenkomen met de "
                    "zichtbare pagina-inhoud."
                ),
                evidence={
                    "source": "json_ld",
                    "schemas": missing,
                    "cause_key": _schema_cause_key(missing),
                },
            )
        )
    if mismatches:
        signals.append(
            IssueSignal(
                issue_type="structured_data_visible_content_mismatch",
                category="structured_data",
                severity="medium",
                confidence="medium",
                title="Structured data wijkt af van zichtbare pagina-inhoud",
                description=(
                    "De primaire naam of kop uit de markup is niet herkenbaar in title, H1 of "
                    "hoofdcontent."
                ),
                recommended_action=(
                    "Maak de primaire schemanaam of headline gelijk aan de inhoud die bezoekers "
                    "werkelijk zien."
                ),
                evidence={
                    "source": "json_ld",
                    "mismatches": mismatches,
                    "cause_key": _schema_cause_key(mismatches),
                },
            )
        )
    if broken_images:
        signals.append(
            IssueSignal(
                issue_type="structured_data_image_unreachable",
                category="structured_data",
                severity="medium",
                confidence="high",
                title="Schema-afbeelding is niet bereikbaar",
                description=(
                    "Een interne afbeelding uit de structured data heeft een gemeten foutstatus."
                ),
                recommended_action=(
                    "Herstel de afbeeldings-URL of vervang hem in pagina en structured data door "
                    "een bereikbare afbeelding."
                ),
                evidence={
                    "source": "json_ld",
                    "images": broken_images,
                    "cause_key": _schema_cause_key(broken_images),
                },
            )
        )
    return signals


def _schema_urls(value: object) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {url for item in value for url in _schema_urls(item)}
    if isinstance(value, dict):
        return {url for key in ("url", "contentUrl", "@id") for url in _schema_urls(value.get(key))}
    return set()


def _has_value(value: object) -> bool:
    return value not in (None, "", [], {})


def _schema_cause_key(value: object) -> str:
    import hashlib
    import json

    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


def _is_deep_content_page(url: Url, snapshot: UrlSnapshot) -> bool:
    parsed = urlsplit(url.normalized_url)
    return bool(
        url.is_active
        and url.current_status_code == 200
        and url.is_indexable is True
        and (url.crawl_depth or 0) >= 2
        and not parsed.query
        and is_probable_html_page(url.normalized_url)
        and snapshot.status_code == 200
        and snapshot.is_indexable is True
        and not snapshot.redirect_chain
    )

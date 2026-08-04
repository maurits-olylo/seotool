from dataclasses import dataclass, field
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.services.issue_engine import reconcile_issues
from app.services.robots import RobotsRules
from app.services.sitemap import SitemapDocument
from app.services.technical_checks import IssueSignal
from app.services.url_scope import is_url_in_website_scope

SITEMAP_QUALITY_ISSUE = "sitemap_document_quality"
ROBOTS_SITEMAP_ISSUE = "robots_sitemap_configuration"
QUALITY_ISSUE_TYPES = {SITEMAP_QUALITY_ISSUE, ROBOTS_SITEMAP_ISSUE}
MAX_EXAMPLES = 10


@dataclass
class SitemapQualityReport:
    documents_checked: int = 0
    missing_locations: int = 0
    duplicate_locations: set[str] = field(default_factory=set)
    invalid_last_modified_locations: set[str] = field(default_factory=set)
    invalid_url_locations: set[str] = field(default_factory=set)
    out_of_scope_locations: set[str] = field(default_factory=set)
    duplicate_robots_sitemaps: set[str] = field(default_factory=set)
    invalid_robots_sitemaps: set[str] = field(default_factory=set)
    out_of_scope_robots_sitemaps: set[str] = field(default_factory=set)
    seen_locations: set[str] = field(default_factory=set)


def record_sitemap_document(
    report: SitemapQualityReport,
    document: SitemapDocument,
    *,
    base_url: str,
    allowed_subdomains: list[str],
) -> None:
    report.documents_checked += 1
    report.missing_locations += document.missing_location_count
    report.duplicate_locations.update(document.duplicate_locations)
    report.invalid_last_modified_locations.update(document.invalid_last_modified_locations)
    for location in (*document.child_sitemaps, *(item.location for item in document.urls)):
        if location in report.seen_locations:
            report.duplicate_locations.add(location)
        report.seen_locations.add(location)
        if not is_absolute_http_url(location):
            report.invalid_url_locations.add(location)
        elif not is_url_in_website_scope(
            location,
            base_url=base_url,
            allowed_subdomains=allowed_subdomains,
        ):
            report.out_of_scope_locations.add(location)


def record_robots_sitemaps(
    report: SitemapQualityReport,
    rules: RobotsRules | None,
    *,
    base_url: str,
    allowed_subdomains: list[str],
) -> None:
    if rules is None:
        return
    seen: set[str] = set()
    for sitemap_url in rules.sitemaps():
        if sitemap_url in seen:
            report.duplicate_robots_sitemaps.add(sitemap_url)
        seen.add(sitemap_url)
        if not is_absolute_http_url(sitemap_url):
            report.invalid_robots_sitemaps.add(sitemap_url)
        elif not is_url_in_website_scope(
            sitemap_url,
            base_url=base_url,
            allowed_subdomains=allowed_subdomains,
        ):
            report.out_of_scope_robots_sitemaps.add(sitemap_url)


def record_sitemap_roots(
    report: SitemapQualityReport,
    sitemap_urls: list[str],
    *,
    base_url: str,
    allowed_subdomains: list[str],
) -> None:
    for sitemap_url in sitemap_urls:
        if not is_absolute_http_url(sitemap_url):
            report.invalid_url_locations.add(sitemap_url)
        elif not is_url_in_website_scope(
            sitemap_url,
            base_url=base_url,
            allowed_subdomains=allowed_subdomains,
        ):
            report.out_of_scope_locations.add(sitemap_url)


def reconcile_sitemap_quality(
    db: Session,
    *,
    website_id: object,
    crawl_run_id: object,
    report: SitemapQualityReport,
) -> None:
    reconcile_issues(
        db,
        website_id=website_id,
        url_id=None,
        crawl_run_id=crawl_run_id,
        snapshot_id=None,
        signals=_quality_signals(report),
        checked_issue_types=QUALITY_ISSUE_TYPES,
    )


def _quality_signals(report: SitemapQualityReport) -> list[IssueSignal]:
    signals: list[IssueSignal] = []
    sitemap_findings = {
        "missing_location_count": report.missing_locations,
        "duplicate_locations": _examples(report.duplicate_locations),
        "invalid_last_modified_locations": _examples(report.invalid_last_modified_locations),
        "invalid_url_locations": _examples(report.invalid_url_locations),
        "out_of_scope_locations": _examples(report.out_of_scope_locations),
    }
    sitemap_count = sum(
        (
            report.missing_locations,
            len(report.duplicate_locations),
            len(report.invalid_last_modified_locations),
            len(report.invalid_url_locations),
            len(report.out_of_scope_locations),
        )
    )
    if sitemap_count:
        signals.append(
            IssueSignal(
                issue_type=SITEMAP_QUALITY_ISSUE,
                category="indexation",
                severity=(
                    "medium" if report.missing_locations or report.invalid_url_locations else "low"
                ),
                confidence="high",
                title=f"Sitemap bevat {sitemap_count} kwaliteitsbevindingen",
                description=(
                    "Een of meer sitemapdocumenten bevatten ontbrekende, dubbele, ongeldige "
                    "of websitevreemde URL-informatie."
                ),
                recommended_action=(
                    "Corrigeer de sitemapgenerator en publiceer alleen unieke, absolute URL's "
                    "met geldige lastmod-waarden binnen deze website."
                ),
                evidence={"documents_checked": report.documents_checked, **sitemap_findings},
            )
        )

    robots_findings = {
        "duplicate_sitemaps": _examples(report.duplicate_robots_sitemaps),
        "invalid_sitemaps": _examples(report.invalid_robots_sitemaps),
        "out_of_scope_sitemaps": _examples(report.out_of_scope_robots_sitemaps),
    }
    robots_count = sum(
        (
            len(report.duplicate_robots_sitemaps),
            len(report.invalid_robots_sitemaps),
            len(report.out_of_scope_robots_sitemaps),
        )
    )
    if robots_count:
        signals.append(
            IssueSignal(
                issue_type=ROBOTS_SITEMAP_ISSUE,
                category="indexation",
                severity="medium" if report.invalid_robots_sitemaps else "low",
                confidence="high",
                title=f"Robots.txt bevat {robots_count} sitemapbevindingen",
                description=(
                    "De sitemapdeclaraties in robots.txt zijn dubbel, ongeldig of verwijzen "
                    "buiten de ingestelde websitescope."
                ),
                recommended_action=(
                    "Publiceer iedere geldige sitemap één keer als absolute URL binnen de "
                    "bedoelde websitescope."
                ),
                evidence=robots_findings,
            )
        )
    return signals


def is_absolute_http_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.hostname)


def _examples(values: set[str]) -> list[str]:
    return sorted(values)[:MAX_EXAMPLES]

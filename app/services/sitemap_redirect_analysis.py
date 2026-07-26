import re
from collections import defaultdict
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.discovery import Url
from app.models.issues import Issue, IssueOccurrence
from app.services.issue_engine import reconcile_issues
from app.services.technical_checks import IssueSignal

SITEMAP_REDIRECT_PATTERN_TYPE = "sitemap_redirect_patterns"
MINIMUM_PATTERN_SIZE = 3

NUMBER_RE = re.compile(r"\d+")


def analyze_sitemap_redirect_patterns(
    db: Session, *, website_id: object, crawl_run_id: object
) -> list[Issue]:
    """Turn repeated sitemap redirects into one actionable website diagnosis."""
    rows = list(
        db.execute(
            select(Issue, Url, IssueOccurrence)
            .join(Url, Url.id == Issue.url_id)
            .join(IssueOccurrence, IssueOccurrence.issue_id == Issue.id)
            .where(
                Issue.website_id == website_id,
                Issue.issue_type == "sitemap_redirect",
                IssueOccurrence.crawl_run_id == crawl_run_id,
            )
            .order_by(Url.normalized_url)
        )
    )
    grouped: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for _issue, url, occurrence in rows:
        final_url = occurrence.evidence.get("final_url")
        if not isinstance(final_url, str) or not final_url:
            continue
        key, label = _redirect_pattern(url.normalized_url, final_url)
        grouped[(key, label)].append((url.normalized_url, final_url))

    patterns: list[dict[str, object]] = []
    covered_urls: set[str] = set()
    for (pattern_key, label), redirects in sorted(grouped.items()):
        unique_redirects = sorted(set(redirects))
        if len(unique_redirects) < MINIMUM_PATTERN_SIZE:
            continue
        urls = [source for source, _target in unique_redirects]
        covered_urls.update(urls)
        patterns.append(
            {
                "pattern": pattern_key,
                "label": label,
                "url_count": len(unique_redirects),
                "urls": urls,
                "examples": [
                    {"sitemap_url": source, "final_url": target}
                    for source, target in unique_redirects[:5]
                ],
            }
        )

    signals: list[IssueSignal] = []
    if patterns:
        signals.append(
            IssueSignal(
                issue_type=SITEMAP_REDIRECT_PATTERN_TYPE,
                category="indexation",
                severity="medium",
                confidence="high",
                title=(
                    f"{len(covered_urls)} sitemap-URL's gebruiken "
                    + (
                        "1 vast redirectpatroon"
                        if len(patterns) == 1
                        else f"{len(patterns)} vaste redirectpatronen"
                    )
                ),
                description=(
                    "De trailing slash of een andere URL-vorm is niet op zichzelf een SEO-fout. "
                    "De sitemap verwijst hier echter herhaaldelijk naar een omweg in plaats van "
                    "rechtstreeks naar de definitieve URL."
                ),
                recommended_action=(
                    "Pas de sitemapgenerator één keer per patroon aan zodat iedere sitemap-URL "
                    "direct de definitieve, canonicale 200-URL gebruikt."
                ),
                evidence={
                    "affected_url_count": len(covered_urls),
                    "pattern_count": len(patterns),
                    "patterns": patterns,
                    "likely_scope": "sitemapgenerator of centrale URL-configuratie",
                    "verification": (
                        "de volgende volledige crawl vindt de betrokken definitieve URL's "
                        "rechtstreeks in de sitemap"
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
        checked_issue_types={SITEMAP_REDIRECT_PATTERN_TYPE},
    )


def _redirect_pattern(source_url: str, final_url: str) -> tuple[str, str]:
    source = urlsplit(source_url)
    target = urlsplit(final_url)
    source_host = (source.hostname or "").lower()
    target_host = (target.hostname or "").lower()

    if (
        source.scheme == target.scheme
        and source.netloc.lower() == target.netloc.lower()
        and source.query == target.query
        and source.path.rstrip("/") == target.path.rstrip("/")
    ):
        if not source.path.endswith("/") and target.path.endswith("/"):
            return "trailing_slash_added", "Trailing slash wordt toegevoegd"
        if source.path.endswith("/") and not target.path.endswith("/"):
            return "trailing_slash_removed", "Trailing slash wordt verwijderd"
    if (
        source.scheme == "http"
        and target.scheme == "https"
        and source_host == target_host
        and source.path == target.path
    ):
        return "http_to_https", "HTTP wordt HTTPS"
    if target_host == f"www.{source_host}":
        return "www_added", "www wordt toegevoegd"
    if source_host == f"www.{target_host}":
        return "www_removed", "www wordt verwijderd"
    if (
        source.scheme == target.scheme
        and source.netloc.lower() == target.netloc.lower()
        and source.path == target.path
        and source.query
        and not target.query
    ):
        return "query_removed", "Queryparameters worden verwijderd"
    source_family = _path_family(source.path)
    target_family = _path_family(target.path)
    return (
        f"path_family:{source_family}->{target_family}",
        f"URL-familie {source_family} stuurt door naar {target_family}",
    )


def _path_family(path: str) -> str:
    parts = [NUMBER_RE.sub("{n}", part) for part in path.strip("/").split("/") if part]
    if not parts:
        return "/"
    if len(parts) == 1:
        return f"/{parts[0]}"
    return "/" + "/".join(parts[:2]) + "/*"

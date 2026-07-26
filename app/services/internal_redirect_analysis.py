import re
from collections import defaultdict
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.discovery import Url
from app.models.issues import Issue, IssueOccurrence
from app.services.issue_engine import reconcile_issues
from app.services.technical_checks import IssueSignal

INTERNAL_REDIRECT_PATTERN_TYPE = "internal_redirect_patterns"
MINIMUM_PATTERN_SIZE = 3
NUMBER_RE = re.compile(r"\d+")


def analyze_internal_redirect_patterns(
    db: Session, *, website_id: object, crawl_run_id: object
) -> list[Issue]:
    """Group redirect targets that share one correctable URL rule."""
    rows = list(
        db.execute(
            select(Issue, Url, IssueOccurrence)
            .join(Url, Url.id == Issue.url_id)
            .join(IssueOccurrence, IssueOccurrence.issue_id == Issue.id)
            .where(
                Issue.website_id == website_id,
                Issue.issue_type == "internally_linked_redirect",
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
        key, label = _pattern(url.normalized_url, final_url)
        grouped[(key, label)].append((url.normalized_url, final_url))

    patterns: list[dict[str, object]] = []
    covered_urls: set[str] = set()
    for (pattern, label), redirects in sorted(grouped.items()):
        unique_redirects = sorted(set(redirects))
        if len(unique_redirects) < MINIMUM_PATTERN_SIZE:
            continue
        urls = [source for source, _target in unique_redirects]
        covered_urls.update(urls)
        patterns.append(
            {
                "pattern": pattern,
                "label": label,
                "url_count": len(urls),
                "urls": urls,
                "examples": [
                    {"redirect_url": source, "final_url": target}
                    for source, target in unique_redirects[:5]
                ],
            }
        )

    signals: list[IssueSignal] = []
    if patterns:
        signals.append(
            IssueSignal(
                issue_type=INTERNAL_REDIRECT_PATTERN_TYPE,
                category="internal_links",
                severity="medium",
                confidence="high",
                title=(
                    f"{len(covered_urls)} interne redirect-URL's volgen "
                    + (
                        "1 vast patroon"
                        if len(patterns) == 1
                        else f"{len(patterns)} vaste patronen"
                    )
                ),
                description=(
                    "Deze redirectdoelen delen dezelfde URL-omzetting. Ze zijn daardoor "
                    "waarschijnlijk één configuratie-, migratie- of componenttaak in plaats "
                    "van losse pagina-acties."
                ),
                recommended_action=(
                    "Zoek per patroon de gedeelde navigatie, component of URL-opbouw en vervang "
                    "de oude doelen centraal door de opgeslagen definitieve URL's."
                ),
                evidence={
                    "affected_url_count": len(covered_urls),
                    "pattern_count": len(patterns),
                    "patterns": patterns,
                    "likely_scope": "gedeelde navigatie, component of URL-migratieregel",
                    "verification": (
                        "de volgende volledige crawl vindt geen interne links meer naar de "
                        "betrokken redirect-URL's"
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
        checked_issue_types={INTERNAL_REDIRECT_PATTERN_TYPE},
    )


def _pattern(source_url: str, final_url: str) -> tuple[str, str]:
    source = urlsplit(source_url)
    target = urlsplit(final_url)
    same_origin = (
        source.scheme == target.scheme
        and source.netloc.lower() == target.netloc.lower()
    )
    if same_origin and source.path.rstrip("/") == target.path.rstrip("/"):
        if not source.path.endswith("/") and target.path.endswith("/"):
            return "trailing_slash_added", "Trailing slash wordt toegevoegd"
        if source.path.endswith("/") and not target.path.endswith("/"):
            return "trailing_slash_removed", "Trailing slash wordt verwijderd"
    if (
        same_origin
        and source.path.lower().endswith((".html", ".htm"))
        and source.path.rsplit(".", 1)[0].rstrip("/") == target.path.rstrip("/")
    ):
        return "legacy_html_extension", "Oude HTML-extensie wordt verwijderd"
    if (
        source.scheme == "http"
        and target.scheme == "https"
        and source.hostname == target.hostname
    ):
        return "http_to_https", "HTTP wordt HTTPS"
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

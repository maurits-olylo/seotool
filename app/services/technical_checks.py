import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from app.models.crawl import UrlSnapshot

THIN_CONTENT_WORD_LIMIT = 150
FUNCTIONAL_PATH_RE = re.compile(
    r"/(?:(?:bedankt|bevestiging|confirmation|thank-you|success|succes)(?:-[^/]*)?|"
    r"inloggen|login|uitloggen|logout|winkelwagen|cart|checkout|afrekenen)(?:/|$)",
    re.IGNORECASE,
)
VARIANT_QUERY_PARAMETERS = {"c", "filter", "page", "paged", "p", "q", "search", "sort"}

SNAPSHOT_ISSUE_TYPES = {
    "http_404",
    "http_410",
    "http_5xx",
    "long_redirect_chain",
    "missing_title",
    "missing_meta_description",
    "missing_h1",
    "multiple_h1",
    "thin_content",
    "unexpected_noindex",
    "canonical_other_url",
    "conflicting_robots",
    "expired_job_posting",
    "expired_job_posting_linked",
    "expired_job_posting_404",
    "job_posting_schema_missing",
    "job_posting_missing_fields",
    "job_posting_invalid_dates",
    "job_posting_missing_application",
    "job_posting_remote_location_missing",
    "job_posting_location_incomplete",
    "job_posting_not_detail_page",
    "job_posting_missing_recommended_fields",
    "robots_txt_blocked",
}


@dataclass(frozen=True)
class IssueSignal:
    issue_type: str
    category: str
    severity: str
    title: str
    description: str
    recommended_action: str
    evidence: dict[str, object]
    confidence: str = "high"


def inspect_snapshot(snapshot: UrlSnapshot) -> list[IssueSignal]:
    signals: list[IssueSignal] = []
    status = snapshot.status_code
    if status in {404, 410}:
        signals.append(
            _signal(
                f"http_{status}",
                "reachability",
                "high",
                f"Pagina geeft {status}",
                "Herstel de pagina of stel een relevante redirect in.",
                status_code=status,
            )
        )
    elif status is not None and status >= 500:
        signals.append(
            _signal(
                "http_5xx",
                "reachability",
                "critical",
                "Serverfout",
                "Onderzoek en herstel de serverfout.",
                status_code=status,
            )
        )
    if len(snapshot.redirect_chain or []) > 3:
        signals.append(
            _signal(
                "long_redirect_chain",
                "reachability",
                "medium",
                "Lange redirectketen",
                "Verkort de redirectketen tot maximaal één stap.",
                redirects=len(snapshot.redirect_chain),
            )
        )
    if snapshot.redirect_chain:
        return signals
    if status == 200 and not snapshot.title:
        signals.append(
            _signal(
                "missing_title",
                "onpage",
                "medium",
                "Title ontbreekt",
                "Voeg een unieke, beschrijvende title toe.",
            )
        )
    if status == 200 and not snapshot.meta_description:
        signals.append(
            _signal(
                "missing_meta_description",
                "onpage",
                "low",
                "Meta description ontbreekt",
                "Voeg een relevante meta description toe.",
            )
        )
    h1_values = (snapshot.headings or {}).get("h1", [])
    if status == 200 and not h1_values:
        signals.append(
            _signal("missing_h1", "onpage", "medium", "H1 ontbreekt", "Voeg één duidelijke H1 toe.")
        )
    elif len(h1_values) > 1:
        signals.append(
            _signal(
                "multiple_h1",
                "onpage",
                "low",
                "Meerdere H1-koppen",
                "Controleer de kopstructuur en gebruik één primaire H1.",
                count=len(h1_values),
            )
        )
    if _should_report_thin_content(snapshot):
        word_count = snapshot.word_count or 0
        nearly_empty = word_count < 30
        signals.append(
            _signal(
                "thin_content",
                "onpage",
                "medium" if nearly_empty else "low",
                "Nagenoeg lege pagina" if nearly_empty else "Beperkte hoofdcontent",
                "Controleer of deze indexeerbare pagina de zoekvraag zelfstandig en volledig "
                "beantwoordt. Een laag woordenaantal is een controlesignaal, "
                "geen automatische fout.",
                word_count=word_count,
                threshold=THIN_CONTENT_WORD_LIMIT,
                content_level="nearly_empty" if nearly_empty else "limited",
                confidence="medium",
            )
        )
    if status == 200 and snapshot.is_indexable is False:
        signals.append(
            _signal(
                "unexpected_noindex",
                "indexation",
                "medium",
                "Pagina heeft een noindex-instructie",
                "Controleer of de noindex bewust is en verwijder hem wanneer de pagina "
                "organisch vindbaar moet zijn.",
            )
        )
    if (
        snapshot.canonical
        and snapshot.final_url
        and _canonical_difference_is_actionable(snapshot.final_url, snapshot.canonical)
    ):
        signals.append(
            _signal(
                "canonical_other_url",
                "indexation",
                "medium",
                "Canonical wijst naar andere URL",
                "Controleer of de afwijkende canonical bewust is.",
                canonical=snapshot.canonical,
            )
        )
    robots = {value for value in [snapshot.meta_robots, snapshot.x_robots_tag] if value}
    if len(robots) > 1 and _robots_conflict(robots):
        signals.append(
            _signal(
                "conflicting_robots",
                "indexation",
                "high",
                "Conflicterende robots-instructies",
                "Maak meta robots en X-Robots-Tag consistent.",
                directives=sorted(robots),
            )
        )
    return signals


def _should_report_thin_content(snapshot: UrlSnapshot) -> bool:
    if (
        snapshot.status_code != 200
        or snapshot.redirect_chain
        or snapshot.is_indexable is False
        or snapshot.word_count is None
        or snapshot.word_count >= THIN_CONTENT_WORD_LIMIT
    ):
        return False
    page_url = snapshot.final_url or snapshot.requested_url
    if not page_url:
        return True
    parsed = urlsplit(page_url)
    if FUNCTIONAL_PATH_RE.search(parsed.path):
        return False
    query_parameters = set(parse_qs(parsed.query, keep_blank_values=True))
    if query_parameters & VARIANT_QUERY_PARAMETERS:
        return False
    return not bool({"SearchResultsPage"} & set(snapshot.schema_types or []))


def _canonical_difference_is_actionable(page_url: str, canonical: str) -> bool:
    if canonical.rstrip("/") == page_url.rstrip("/"):
        return False
    page = urlsplit(page_url)
    target = urlsplit(canonical)
    same_page = (
        page.scheme.lower(),
        page.netloc.lower(),
        page.path.rstrip("/"),
    ) == (
        target.scheme.lower(),
        target.netloc.lower(),
        target.path.rstrip("/"),
    )
    if not same_page or target.query:
        return True
    query_keys = set(parse_qs(page.query, keep_blank_values=True))
    return bool(query_keys & {"page", "paged", "p"})


def _signal(
    issue_type: str,
    category: str,
    severity: str,
    title: str,
    action: str,
    confidence: str = "high",
    **evidence: object,
) -> IssueSignal:
    return IssueSignal(issue_type, category, severity, title, title, action, evidence, confidence)


def _robots_conflict(values: set[str]) -> bool:
    combined = [value.lower() for value in values]
    return any("noindex" in value for value in combined) and any(
        "index" in value and "noindex" not in value for value in combined
    )

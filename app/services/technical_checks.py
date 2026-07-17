import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from urllib.parse import parse_qs, urlsplit

from app.models.crawl import UrlSnapshot
from app.services.html_extraction import INVALID_JSON_LD_MARKER
from app.services.http_crawler import CrawlError

THIN_CONTENT_WORD_LIMIT = 150
OUTDATED_CONTENT_AGE_DAYS = 3 * 365
EDITORIAL_SCHEMA_TYPES = {"Article", "BlogPosting", "NewsArticle", "TechArticle"}
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
    "crawl_timeout",
    "redirect_loop",
    "unreachable_url_target",
    "long_redirect_chain",
    "missing_title",
    "missing_meta_description",
    "missing_h1",
    "multiple_h1",
    "thin_content",
    "possibly_outdated_content",
    "canonical_other_url",
    "conflicting_robots",
    "invalid_json_ld",
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
    "duplicate_heading_text",
    "cms_link_placeholder",
    "invalid_or_empty_link",
    "broken_application_cta",
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


CRAWL_ERROR_ISSUE_TYPES = {"crawl_timeout", "redirect_loop", "unreachable_url_target"}


def inspect_crawl_error(error: CrawlError) -> list[IssueSignal]:
    if error.error_type == "invalid_target":
        return [
            _signal(
                "unreachable_url_target",
                "reachability",
                "medium",
                "URL-doel kan niet worden bereikt",
                "Controleer of hostname en URL nog bestaan en werk interne links naar een "
                "bereikbare HTTPS-bestemming bij.",
                confidence="medium",
                error_type=error.error_type,
                error_message=str(error),
            )
        ]
    if error.error_type == "timeout":
        return [
            _signal(
                "crawl_timeout",
                "reachability",
                "high",
                "Pagina reageert niet binnen de ingestelde tijd",
                "Controleer de serverbelasting, bereikbaarheid en ingestelde time-out. "
                "Probeer de URL daarna opnieuw.",
                error_type=error.error_type,
                error_message=str(error),
            )
        ]
    if error.error_type == "redirect_loop":
        return [
            _signal(
                "redirect_loop",
                "reachability",
                "high",
                "Redirectloop gedetecteerd",
                "Corrigeer de redirectregels zodat de URL in één doorlopende keten op een "
                "bereikbare eind-URL uitkomt.",
                error_type=error.error_type,
                error_message=str(error),
            )
        ]
    return []


def inspect_snapshot(snapshot: UrlSnapshot, *, today: date | None = None) -> list[IssueSignal]:
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
    inspect_onpage = status == 200 and snapshot.is_indexable is not False
    if inspect_onpage and not snapshot.title:
        signals.append(
            _signal(
                "missing_title",
                "onpage",
                "medium",
                "Title ontbreekt",
                "Voeg een unieke, beschrijvende title toe.",
            )
        )
    if inspect_onpage and not snapshot.meta_description:
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
    if inspect_onpage and not h1_values:
        signals.append(
            _signal("missing_h1", "onpage", "medium", "H1 ontbreekt", "Voeg één duidelijke H1 toe.")
        )
    elif inspect_onpage and len(h1_values) > 1:
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
    invalid_json_ld_blocks = sum(
        1
        for value in snapshot.schema_data or []
        if isinstance(value, dict) and value.get(INVALID_JSON_LD_MARKER) is True
    )
    if status == 200 and invalid_json_ld_blocks:
        signals.append(
            _signal(
                "invalid_json_ld",
                "structured_data",
                "medium",
                "JSON-LD kan niet worden gelezen",
                "Herstel de JSON-syntax en valideer de structured data opnieuw.",
                invalid_blocks=invalid_json_ld_blocks,
            )
        )
    outdated_signal = _possibly_outdated_content_signal(
        snapshot,
        today=today or datetime.now(UTC).date(),
    )
    if outdated_signal:
        signals.append(outdated_signal)
    return signals


def _possibly_outdated_content_signal(
    snapshot: UrlSnapshot,
    *,
    today: date,
) -> IssueSignal | None:
    if snapshot.status_code != 200 or snapshot.redirect_chain or snapshot.is_indexable is False:
        return None
    dated_nodes = _editorial_schema_dates(snapshot.schema_data or [])
    if not dated_nodes:
        return None
    source, content_date = max(dated_nodes, key=lambda item: item[1])
    age_days = (today - content_date).days
    if age_days < OUTDATED_CONTENT_AGE_DAYS or content_date > today:
        return None
    return _signal(
        "possibly_outdated_content",
        "content",
        "low",
        "Redactionele content mogelijk verouderd",
        "Controleer of de inhoud nog actueel en nuttig is. Werk de pagina inhoudelijk bij, "
        "behoud hem bewust of voeg een passende redirect toe; wijzig de datum niet zonder "
        "inhoudelijke update.",
        confidence="low",
        content_date=content_date.isoformat(),
        date_source=source,
        age_days=age_days,
        threshold_days=OUTDATED_CONTENT_AGE_DAYS,
    )


def _editorial_schema_dates(values: list[object]) -> list[tuple[str, date]]:
    found: list[tuple[str, date]] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            schema_type = value.get("@type")
            types = (
                {schema_type}
                if isinstance(schema_type, str)
                else {item for item in schema_type if isinstance(item, str)}
                if isinstance(schema_type, list)
                else set()
            )
            if types & EDITORIAL_SCHEMA_TYPES:
                for field in ("dateModified", "datePublished"):
                    parsed = _parse_schema_date(value.get(field))
                    if parsed:
                        found.append((field, parsed))
                        break
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(values)
    return found


def _parse_schema_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


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

import re
from urllib.parse import parse_qs, urlsplit

from app.models.crawl import UrlSnapshot
from app.services.technical_checks import IssueSignal
from app.services.url_normalization import InvalidUrlError, normalize_url

STRONG_NOT_FOUND_RE = re.compile(
    r"\b(?:404|pagina\s+(?:kan\s+)?niet\s+gevonden|pagina\s+bestaat\s+niet|"
    r"page\s+not\s+found|page\s+does\s+not\s+exist|seite\s+nicht\s+gefunden|"
    r"page\s+introuvable)\b",
    re.IGNORECASE,
)
EMPTY_RESULT_RE = re.compile(
    r"\b(?:geen\s+(?:zoek)?resultaten|niets\s+gevonden|no\s+(?:search\s+)?results|"
    r"no\s+matches|keine\s+ergebnisse|aucun\s+r[ée]sultat)\b",
    re.IGNORECASE,
)
FUNCTIONAL_QUERY_PARAMETERS = {"filter", "page", "paged", "q", "query", "s", "search"}
FUNCTIONAL_PATH_RE = re.compile(r"/(?:search|zoeken|zoekresultaten|filter)(?:/|$)", re.I)
NEARLY_EMPTY_WORD_LIMIT = 60


def inspect_soft_404(
    snapshot: UrlSnapshot, *, previous: UrlSnapshot | None = None
) -> list[IssueSignal]:
    if (
        snapshot.status_code != 200
        or snapshot.redirect_chain
        or snapshot.is_indexable is False
        or not _is_html(snapshot)
    ):
        return []
    title_and_h1 = " ".join(
        [snapshot.title or "", *((snapshot.headings or {}).get("h1", []))]
    )
    content = snapshot.main_content or ""
    strong_marker = bool(STRONG_NOT_FOUND_RE.search(title_and_h1))
    content_marker = bool(STRONG_NOT_FOUND_RE.search(content[:2000]))
    empty_result_marker = bool(
        EMPTY_RESULT_RE.search(f"{title_and_h1} {content[:2000]}")
    )
    nearly_empty = (snapshot.word_count or 0) <= NEARLY_EMPTY_WORD_LIMIT
    canonical_elsewhere = _canonical_points_elsewhere(snapshot)
    previously_missing = bool(previous and previous.status_code in {404, 410})
    evidence = {
        "status_code": snapshot.status_code,
        "word_count": snapshot.word_count or 0,
        "threshold": NEARLY_EMPTY_WORD_LIMIT,
        "title_or_h1_not_found_marker": strong_marker,
        "content_not_found_marker": content_marker,
        "empty_result_marker": empty_result_marker,
        "canonical": snapshot.canonical,
        "canonical_points_elsewhere": canonical_elsewhere,
        "previous_status_code": previous.status_code if previous else None,
    }
    strong_evidence_count = sum(
        [
            strong_marker,
            content_marker and nearly_empty,
            canonical_elsewhere and (strong_marker or content_marker),
            previously_missing and (strong_marker or content_marker),
        ]
    )
    if strong_evidence_count >= 2:
        return [
            IssueSignal(
                issue_type="soft_404",
                category="indexation",
                severity="high",
                confidence="high",
                title="Pagina lijkt een soft 404",
                description=(
                    "De URL geeft status 200, maar meerdere onafhankelijke signalen tonen een "
                    "niet-gevondenpagina. Zoekmachines kunnen deze URL daarom als soft 404 zien."
                ),
                recommended_action=(
                    "Geef 404 of 410 wanneer de pagina echt ontbreekt. Herstel inhoud en canonical "
                    "wanneer de URL wel moet bestaan en controleer daarna opnieuw."
                ),
                evidence={**evidence, "strong_evidence_count": strong_evidence_count},
            )
        ]
    if empty_result_marker and (nearly_empty or _is_functional_result_url(snapshot)):
        return [
            IssueSignal(
                issue_type="possible_soft_404",
                category="indexation",
                severity="low",
                confidence="low",
                title="Lege resultaatpagina vraagt beoordeling",
                description=(
                    "De pagina geeft status 200 en toont geen resultaten. Dit kan een geldige "
                    "zoek- of filtertoestand zijn, maar ook indexeerbare soft-404-ruis."
                ),
                recommended_action=(
                    "Beoordeel of deze resultaat-URL organische waarde heeft. Houd hem functioneel "
                    "maar niet-indexeerbaar, of geef een passende foutstatus wanneer de URL niet "
                    "hoort te bestaan."
                ),
                evidence=evidence,
            )
        ]
    return []


def _canonical_points_elsewhere(snapshot: UrlSnapshot) -> bool:
    if not snapshot.canonical:
        return False
    page_url = snapshot.final_url or snapshot.requested_url
    try:
        return normalize_url(snapshot.canonical) != normalize_url(page_url)
    except InvalidUrlError:
        return True


def _is_functional_result_url(snapshot: UrlSnapshot) -> bool:
    split = urlsplit(snapshot.final_url or snapshot.requested_url)
    return bool(
        FUNCTIONAL_PATH_RE.search(split.path)
        or FUNCTIONAL_QUERY_PARAMETERS.intersection(parse_qs(split.query))
    )


def _is_html(snapshot: UrlSnapshot) -> bool:
    content_type = (snapshot.content_type or "text/html").split(";", 1)[0].lower()
    return content_type in {"text/html", "application/xhtml+xml"}

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.models.crawl import UrlSnapshot
from app.models.discovery import Url
from app.services.html_extraction import ExtractedPage
from app.services.technical_checks import IssueSignal
from app.services.url_normalization import InvalidUrlError, normalize_url

MAX_RENDER_CANDIDATES = 10
LOW_STATIC_WORD_COUNT = 50
MATERIAL_RENDERED_WORD_COUNT = 150
_PATH_VALUE = re.compile(r"^(?:\d+|[0-9a-f]{8,}|[a-z0-9_-]*\d[a-z0-9_-]*)$", re.I)


@dataclass(frozen=True)
class RenderCandidate:
    url: Url
    snapshot: UrlSnapshot
    reasons: tuple[str, ...]
    priority: int


def select_render_candidates(
    records: list[tuple[Url, UrlSnapshot]], *, limit: int = MAX_RENDER_CANDIDATES
) -> list[RenderCandidate]:
    """Select only pages with concrete render risk, capped and template-diverse."""
    selection_limit = max(0, min(limit, MAX_RENDER_CANDIDATES))
    if selection_limit == 0:
        return []
    candidates: list[RenderCandidate] = []
    for url, snapshot in records:
        if not _eligible(url, snapshot):
            continue
        reasons: list[str] = []
        priority = 0
        if url.is_important:
            reasons.append("important_url")
            priority += 100
        if not (snapshot.main_content or "").strip():
            reasons.append("empty_static_content")
            priority += 80
        elif (snapshot.word_count or 0) <= LOW_STATIC_WORD_COUNT:
            reasons.append("low_static_word_count")
            priority += 60
        if snapshot.title is None and not (snapshot.headings or {}).get("h1"):
            reasons.append("missing_static_metadata")
            priority += 40
        if reasons:
            candidates.append(RenderCandidate(url, snapshot, tuple(reasons), priority))

    selected: list[RenderCandidate] = []
    seen_templates: set[str] = set()
    for candidate in sorted(
        candidates, key=lambda item: (-item.priority, item.url.normalized_url)
    ):
        template = _path_template(candidate.url.normalized_url)
        if template in seen_templates and not candidate.url.is_important:
            continue
        seen_templates.add(template)
        selected.append(candidate)
        if len(selected) >= selection_limit:
            break
    return selected


def compare_rendered_page(
    snapshot: UrlSnapshot,
    rendered: ExtractedPage,
    *,
    static_internal_links: set[str] | None = None,
) -> dict[str, object]:
    static_words = snapshot.word_count or 0
    rendered_words = rendered.word_count
    static_links = {_normal_url(value) for value in (static_internal_links or set())}
    rendered_links = {
        normalized
        for link in rendered.links
        if link.is_internal and (normalized := _normal_url(link.target_url))
    }
    js_only_links = sorted(rendered_links - static_links)
    comparison: dict[str, object] = {
        "static_word_count": static_words,
        "rendered_word_count": rendered_words,
        "word_count_delta": rendered_words - static_words,
        "main_content_changed": snapshot.main_content_hash != rendered.main_content_hash,
        "metadata_changed": snapshot.metadata_hash != rendered.metadata_hash,
        "canonical_changed": snapshot.canonical != rendered.canonical,
        "robots_changed": (snapshot.meta_robots or "") != (rendered.meta_robots or ""),
        "structured_data_changed": snapshot.schema_hash != rendered.schema_hash,
        "javascript_only_link_count": len(js_only_links),
        "javascript_only_links": js_only_links[:100],
    }
    comparison["javascript_dependent_content"] = (
        static_words <= LOW_STATIC_WORD_COUNT
        and rendered_words >= MATERIAL_RENDERED_WORD_COUNT
        and rendered_words >= max(1, static_words) * 3
    )
    comparison["rendered_content_missing"] = (
        static_words >= MATERIAL_RENDERED_WORD_COUNT and rendered_words * 2 < static_words
    )
    return comparison


def render_issue_signals(comparison: dict[str, object]) -> list[IssueSignal]:
    signals: list[IssueSignal] = []
    if comparison.get("javascript_dependent_content"):
        signals.append(
            _signal(
                "javascript_dependent_content",
                "Belangrijke inhoud verschijnt pas na JavaScript",
                "De gewone HTML bevat vrijwel geen inhoud, terwijl de browserweergave wel "
                "substantiële content bevat.",
                "Lever de hoofdinhoud server-side of via prerendering en controleer daarna "
                "opnieuw.",
                comparison,
                severity="high",
            )
        )
    if comparison.get("rendered_content_missing"):
        signals.append(
            _signal(
                "rendered_content_missing",
                "Inhoud verdwijnt tijdens browserweergave",
                "De gerenderde pagina bevat materieel minder inhoud dan de ontvangen HTML.",
                "Controleer JavaScript-fouten, conditionele rendering en consentlogica.",
                comparison,
            )
        )
    if int(comparison.get("javascript_only_link_count", 0)) > 0:
        signals.append(
            _signal(
                "javascript_only_links",
                "Interne links zijn alleen na JavaScript beschikbaar",
                "De browserweergave bevat interne links die niet in de gewone HTML stonden.",
                "Plaats belangrijke navigatielinks als crawlbare a[href]-links in de server-HTML.",
                comparison,
            )
        )
    if any(
        comparison.get(key)
        for key in ("canonical_changed", "robots_changed", "structured_data_changed")
    ):
        signals.append(
            _signal(
                "javascript_metadata_conflict",
                "SEO-instructies wijzigen na JavaScript",
                "Canonical, robots of structured data wijkt na browserweergave af van de HTML.",
                "Maak de SEO-instructies in HTML en browserweergave gelijk en voorspelbaar.",
                comparison,
            )
        )
    return signals


def _eligible(url: Url, snapshot: UrlSnapshot) -> bool:
    return bool(
        url.is_active
        and snapshot.status_code == 200
        and snapshot.is_indexable is not False
        and (snapshot.content_type or "").lower().startswith("text/html")
    )


def _path_template(value: str) -> str:
    parts = [part for part in urlsplit(value).path.split("/") if part]
    return "/" + "/".join("{value}" if _PATH_VALUE.match(part) else part for part in parts)


def _normal_url(value: str) -> str:
    try:
        return normalize_url(value)
    except InvalidUrlError:
        return value


def _signal(
    issue_type: str,
    title: str,
    description: str,
    action: str,
    evidence: dict[str, object],
    *,
    severity: str = "medium",
) -> IssueSignal:
    return IssueSignal(
        issue_type=issue_type,
        category="rendering",
        severity=severity,
        confidence="high",
        title=title,
        description=description,
        recommended_action=action,
        evidence=evidence,
    )

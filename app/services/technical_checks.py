from dataclasses import dataclass

from app.models.crawl import UrlSnapshot


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
    if status == 200 and snapshot.word_count is not None and snapshot.word_count < 50:
        signals.append(
            _signal(
                "thin_content",
                "onpage",
                "low",
                "Zeer weinig hoofdcontent",
                "Controleer of de pagina voldoende nuttige hoofdcontent bevat.",
                word_count=snapshot.word_count,
                confidence="medium",
            )
        )
    if status == 200 and snapshot.is_indexable is False:
        signals.append(
            _signal(
                "unexpected_noindex",
                "indexation",
                "high",
                "Pagina is niet indexeerbaar",
                "Controleer robots-instructies en verwijder een onbedoelde noindex.",
            )
        )
    if (
        snapshot.canonical
        and snapshot.final_url
        and snapshot.canonical.rstrip("/") != snapshot.final_url.rstrip("/")
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

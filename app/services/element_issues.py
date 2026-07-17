from collections import Counter

from app.models.crawl import ElementLocation
from app.services.technical_checks import IssueSignal

ELEMENT_ISSUE_TYPES = {
    "duplicate_heading_text",
    "cms_link_placeholder",
    "invalid_or_empty_link",
    "broken_application_cta",
}


def inspect_element_locations(locations: list[ElementLocation]) -> list[IssueSignal]:
    signals: list[IssueSignal] = []
    duplicate_headings = [
        item
        for item in locations
        if "duplicate_heading_text" in item.issue_types
    ]
    if duplicate_headings:
        counts = Counter(
            (item.element_type, item.visible_text or "") for item in duplicate_headings
        )
        labels = [
            f"{element_type.upper()} ‘{text}’ ({count}×)"
            for (element_type, text), count in sorted(counts.items())
        ]
        signals.append(
            IssueSignal(
                issue_type="duplicate_heading_text",
                category="onpage",
                severity="low",
                title="Dezelfde headingtekst komt meerdere keren voor",
                description="; ".join(labels),
                recommended_action=(
                    "Controleer of iedere herhaalde kop een eigen sectie beschrijft. Maak de tekst "
                    "specifieker of verwijder de dubbele kop wanneer dezelfde structuur onbedoeld "
                    "wordt herhaald."
                ),
                evidence={"duplicate_headings": labels},
                confidence="high",
            )
        )
    definitions = {
        "cms_link_placeholder": (
            "medium",
            "Onverwerkte CMS-linkplaceholder",
            "Een link bevat nog template- of CMS-syntax en kan bezoekers niet betrouwbaar sturen.",
            "Vervang de placeholder in het CMS of template door de definitieve URL.",
        ),
        "invalid_or_empty_link": (
            "medium",
            "Lege of onbruikbare link",
            "Een bestaand linkelement heeft geen bruikbare bestemming.",
            "Vul een geldige bestemming in of verwijder het linkgedrag van het element.",
        ),
        "broken_application_cta": (
            "high",
            "Sollicitatieknop heeft geen werkende bestemming",
            "Een bestaande sollicitatie-CTA heeft geen bruikbare link of formulierbestemming.",
            "Koppel de CTA aan het werkende sollicitatieformulier en test de volledige route.",
        ),
    }
    for issue_type, (severity, title, description, action) in definitions.items():
        matching = [item for item in locations if issue_type in item.issue_types]
        if not matching:
            continue
        signals.append(
            IssueSignal(
                issue_type=issue_type,
                category="internal_links" if issue_type != "broken_application_cta" else "content",
                severity=severity,
                title=title,
                description=description,
                recommended_action=action,
                evidence={"element_count": len(matching)},
                confidence="high",
            )
        )
    return signals

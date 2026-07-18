from app.models.crawl import ElementLocation
from app.services.technical_checks import IssueSignal

ELEMENT_ISSUE_TYPES = {
    "cms_link_placeholder",
    "broken_application_cta",
}


def inspect_element_locations(locations: list[ElementLocation]) -> list[IssueSignal]:
    signals: list[IssueSignal] = []
    definitions = {
        "cms_link_placeholder": (
            "medium",
            "Onverwerkte CMS-linkplaceholder",
            "Een link bevat nog template- of CMS-syntax en kan bezoekers niet betrouwbaar sturen.",
            "Vervang de placeholder in het CMS of template door de definitieve URL.",
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

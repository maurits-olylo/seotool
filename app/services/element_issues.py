from app.models.crawl import ElementLocation
from app.services.technical_checks import IssueSignal

ELEMENT_ISSUE_TYPES = {
    "cms_link_placeholder",
    "broken_application_cta",
    "image_alt_missing",
    "functional_image_alt_empty",
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
        "image_alt_missing": (
            "medium",
            "Afbeelding mist een alt-attribuut",
            (
                "Een inhoudelijke afbeelding heeft geen alt-attribuut. Daardoor ontbreekt een "
                "tekstalternatief voor hulptechnologie en beeldcontext."
            ),
            (
                "Voeg een korte, contextuele alt-tekst toe. Gebruik alleen alt=\"\" wanneer de "
                "afbeelding aantoonbaar decoratief is."
            ),
        ),
        "functional_image_alt_empty": (
            "high",
            "Functionele afbeelding heeft geen toegankelijke naam",
            (
                "Een gelinkte afbeelding of afbeeldingsknop heeft een lege alt-tekst en geen "
                "andere toegankelijke naam."
            ),
            (
                "Geef de afbeelding een beschrijvende alt-tekst of geef de omringende link of "
                "knop een duidelijke toegankelijke naam."
            ),
        ),
    }
    for issue_type, (severity, title, description, action) in definitions.items():
        matching = [item for item in locations if issue_type in item.issue_types]
        if not matching:
            continue
        signals.append(
            IssueSignal(
                issue_type=issue_type,
                category=(
                    "internal_links"
                    if issue_type == "cms_link_placeholder"
                    else "content"
                ),
                severity=severity,
                title=title,
                description=description,
                recommended_action=action,
                evidence={
                    "element_count": len(matching),
                    **(
                        {
                            "image_urls": sorted(
                                {
                                    item.target_url
                                    for item in matching
                                    if item.element_type == "img" and item.target_url
                                }
                            )[:100]
                        }
                        if issue_type
                        in {"image_alt_missing", "functional_image_alt_empty"}
                        else {}
                    ),
                },
                confidence="high",
            )
        )
    return signals

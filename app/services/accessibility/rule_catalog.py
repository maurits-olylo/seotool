from dataclasses import dataclass

AXE_CORE_VERSION = "4.12.1"
AXE_SOURCE_PATH = "/opt/axe/axe.min.js"
MAX_ACCESSIBILITY_NODES = 100
MAX_NODES_PER_RULE = 10


@dataclass(frozen=True)
class AccessibilityRule:
    rule_id: str
    title: str
    action: str
    severity: str = "medium"


PILOT_RULES = (
    AccessibilityRule(
        "button-name",
        "Knop heeft geen toegankelijke naam",
        "Geef de knop een duidelijke zichtbare tekst of toegankelijke naam.",
        "high",
    ),
    AccessibilityRule(
        "link-name",
        "Link heeft geen toegankelijke naam",
        "Geef de link een duidelijke zichtbare tekst of toegankelijke naam.",
        "high",
    ),
    AccessibilityRule(
        "image-alt",
        "Afbeelding mist passende alternatieve tekst",
        "Voeg betekenisvolle alt-tekst toe of markeer de afbeelding correct als decoratief.",
    ),
    AccessibilityRule(
        "label",
        "Formulierveld heeft geen gekoppeld label",
        "Koppel een zichtbaar label aan het formulierveld.",
        "high",
    ),
    AccessibilityRule(
        "html-has-lang",
        "Paginataal ontbreekt",
        "Voeg een geldige lang-attribuutwaarde toe aan het html-element.",
    ),
    AccessibilityRule(
        "html-lang-valid",
        "Paginataal is ongeldig",
        "Gebruik een geldige BCP 47-taalcode op het html-element.",
    ),
    AccessibilityRule(
        "document-title",
        "Paginatitel ontbreekt",
        "Voeg een beschrijvende title toe aan het document.",
    ),
    AccessibilityRule(
        "heading-order",
        "Kopstructuur slaat een niveau over",
        "Maak de kopvolgorde logisch zonder niveaus over te slaan.",
    ),
    AccessibilityRule(
        "aria-allowed-attr",
        "ARIA-attribuut is hier niet toegestaan",
        "Verwijder of corrigeer het ARIA-attribuut voor deze rol.",
    ),
    AccessibilityRule(
        "aria-valid-attr-value",
        "ARIA-attribuut heeft een ongeldige waarde",
        "Gebruik een geldige waarde voor het ARIA-attribuut.",
        "high",
    ),
)

PILOT_RULE_IDS = tuple(rule.rule_id for rule in PILOT_RULES)
PILOT_RULE_BY_ID = {rule.rule_id: rule for rule in PILOT_RULES}
ACCESSIBILITY_ISSUE_TYPES = {
    f"accessibility_{rule_id.replace('-', '_')}" for rule_id in PILOT_RULE_IDS
}

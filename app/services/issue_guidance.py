from dataclasses import dataclass

from app.models.issues import Issue


@dataclass(frozen=True)
class GuidanceStatement:
    text: str
    basis: str


CATEGORY_RELEVANCE = {
    "reachability": "Bezoekers en zoekmachines kunnen de URL mogelijk niet betrouwbaar bereiken.",
    "indexation": "Dit signaal kan beïnvloeden welke URL zoekmachines crawlen of indexeren.",
    "onpage": (
        "Dit onderdeel helpt zoekmachines en bezoekers het onderwerp van de pagina begrijpen."
    ),
    "internal_links": (
        "Interne links bepalen bereikbaarheid, gebruikersroutes en de verdeling van interne "
        "autoriteit."
    ),
    "structured_data": (
        "Ongeldige of onvolledige structured data kan uitgebreide zoekresultaten verhinderen."
    ),
    "content": (
        "De inhoud vraagt menselijke beoordeling op volledigheid, actualiteit of zoekintentie."
    ),
}

VERIFICATION_BY_TYPE = {
    "http_404": (
        "De URL geeft na de volgende crawl de bedoelde 200-status of één relevante redirect."
    ),
    "http_410": (
        "De verwijdering is bewust en er bestaan geen ongewenste sitemap- of interne links meer."
    ),
    "http_5xx": "De URL reageert bij de volgende crawl stabiel zonder serverfout.",
    "crawl_timeout": "De URL reageert binnen de ingestelde time-out tijdens de volgende controle.",
    "redirect_loop": "De URL komt zonder lus op één bereikbare eind-URL uit.",
    "long_redirect_chain": "De URL bereikt de bedoelde eindbestemming in maximaal één redirect.",
    "missing_title": "De volgende crawl vindt één niet-lege, beschrijvende title.",
    "missing_meta_description": "De volgende crawl vindt een niet-lege meta description.",
    "missing_h1": "De volgende crawl vindt één duidelijke primaire H1.",
    "multiple_h1": "De volgende crawl vindt de bewust gekozen kopstructuur met één primaire H1.",
    "canonical_other_url": (
        "De canonical wijst na controle bewust naar de gewenste indexeerbare URL."
    ),
    "conflicting_robots": (
        "Meta robots en X-Robots-Tag bevatten bij de volgende crawl geen conflict."
    ),
    "invalid_json_ld": "Alle JSON-LD-blokken zijn leesbaar en opnieuw gevalideerd.",
    "internally_linked_404": "Geen interne bronpagina linkt nog naar dit 404-doel.",
    "internally_linked_redirect": "Interne links wijzen rechtstreeks naar de definitieve 200-URL.",
    "orphan_page": (
        "De pagina heeft een bewuste interne route of is bewust buiten de navigatie gehouden."
    ),
}

OBSERVATION_BY_TYPE = {
    "missing_title": (
        "De laatste analyse heeft geen title voor deze indexeerbare pagina opgeslagen."
    ),
    "missing_meta_description": (
        "De laatste analyse heeft geen meta description voor deze pagina opgeslagen."
    ),
    "missing_h1": "De laatste analyse heeft geen H1 voor deze pagina opgeslagen.",
    "multiple_h1": "De laatste analyse heeft meerdere H1-koppen op deze pagina opgeslagen.",
    "http_404": "De laatst opgeslagen HTTP-status voor deze URL is 404.",
    "http_410": "De laatst opgeslagen HTTP-status voor deze URL is 410.",
    "http_5xx": "De laatst opgeslagen HTTP-status is een serverfout.",
    "invalid_json_ld": "Minstens één opgeslagen JSON-LD-blok kon niet worden gelezen.",
}


def build_issue_guidance(issue: Issue, evidence: dict[str, object]) -> dict[str, object]:
    relevance = CATEGORY_RELEVANCE.get(
        issue.category,
        "Dit signaal wijkt af van de verwachte technische of inhoudelijke toestand.",
    )
    likely_cause = evidence.get("likely_cause")
    if isinstance(likely_cause, str) and likely_cause.strip():
        cause = GuidanceStatement(likely_cause.strip(), "interpretation")
    else:
        observation = OBSERVATION_BY_TYPE.get(
            issue.issue_type,
            "De laatste controle bevestigt het signaal, maar stelt de onderliggende "
            "oorzaak niet vast.",
        )
        cause = GuidanceStatement(observation, "fact")

    alternative = evidence.get("alternative_explanation")
    alternative_statement = (
        GuidanceStatement(alternative.strip(), "hypothesis")
        if isinstance(alternative, str) and alternative.strip()
        else GuidanceStatement(
            "Er is nog geen alternatieve oorzaak bewezen; controleer de pagina of "
            "configuratie vóór aanpassing.",
            "hypothesis",
        )
    )
    verification = evidence.get("verification")
    verification_text = (
        verification.strip()
        if isinstance(verification, str) and verification.strip()
        else VERIFICATION_BY_TYPE.get(
            issue.issue_type,
            "Hetzelfde signaal is na een succesvolle volgende crawl niet meer aanwezig.",
        )
    )
    action = issue.recommended_action.strip()
    return {
        "relevance": {"text": relevance, "basis": "interpretation"},
        "likely_cause": {"text": cause.text, "basis": cause.basis},
        "alternative_explanation": {
            "text": alternative_statement.text,
            "basis": alternative_statement.basis,
        },
        "steps": [action]
        if action
        else ["Beoordeel het opgeslagen bewijs en bepaal de passende wijziging."],
        "verification": verification_text,
        "confidence": issue.confidence,
    }

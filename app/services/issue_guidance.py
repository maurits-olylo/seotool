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

TYPE_RELEVANCE = {
    "duplicate_heading_text": (
        "Herhaalde kopteksten kunnen de inhoudsstructuur onduidelijk maken. Herhaling in vaste "
        "interfaceblokken kan bewust zijn en vraagt dan geen aanpassing."
    ),
    "job_posting_schema_missing": (
        "Zonder JobPosting-schema kan Google deze vacature niet betrouwbaar als vacature herkennen."
    ),
    "multiple_broken_internal_links": (
        "Meerdere dode links onderbreken dezelfde gebruikersroute en verspillen crawlverkeer."
    ),
    "patterned_404_urls": (
        "Een terugkerend 404-patroon wijst op structurele URL-generatie en kan veel "
        "ruis veroorzaken."
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
    "duplicate_heading_text": (
        "De volgende crawl vindt geen onbedoeld herhaalde koptekst meer; bewuste UI-herhaling is "
        "als zodanig beoordeeld."
    ),
    "job_posting_schema_missing": (
        "De volgende crawl vindt geldig JobPosting-schema op de vacaturedetailpagina."
    ),
}


def build_issue_guidance(issue: Issue, evidence: dict[str, object]) -> dict[str, object]:
    relevance = TYPE_RELEVANCE.get(
        issue.issue_type,
        CATEGORY_RELEVANCE.get(
            issue.category,
            "Dit signaal wijkt af van de verwachte technische of inhoudelijke toestand.",
        ),
    )
    likely_cause = evidence.get("likely_cause")
    if isinstance(likely_cause, str) and likely_cause.strip():
        cause = GuidanceStatement(likely_cause.strip(), "interpretation")
    else:
        cause = None

    alternative = evidence.get("alternative_explanation")
    alternative_statement = (
        GuidanceStatement(alternative.strip(), "hypothesis")
        if isinstance(alternative, str) and alternative.strip()
        else None
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
        "likely_cause": {"text": cause.text, "basis": cause.basis} if cause else None,
        "alternative_explanation": (
            {"text": alternative_statement.text, "basis": alternative_statement.basis}
            if alternative_statement
            else None
        ),
        "steps": [action]
        if action
        else ["Beoordeel het opgeslagen bewijs en bepaal de passende wijziging."],
        "verification": verification_text,
        "confidence": issue.confidence,
    }

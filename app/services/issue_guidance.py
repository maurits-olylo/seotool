from dataclasses import dataclass

from app.models.issues import Issue


@dataclass(frozen=True)
class GuidanceStatement:
    text: str
    basis: str


@dataclass(frozen=True)
class GuidanceSource:
    title: str
    url: str
    publisher: str = "Google Search Central"


SOURCES = {
    "http": GuidanceSource(
        "HTTP-statuscodes en netwerkfouten",
        "https://developers.google.com/search/docs/crawling-indexing/http-network-errors",
    ),
    "redirect": GuidanceSource(
        "Redirects en Google Search",
        "https://developers.google.com/search/docs/crawling-indexing/301-redirects",
    ),
    "canonical": GuidanceSource(
        "Canonical URL's en dubbele URL's",
        "https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls",
    ),
    "robots": GuidanceSource(
        "Robots meta tags en X-Robots-Tag",
        "https://developers.google.com/search/docs/crawling-indexing/robots-meta-tag",
    ),
    "robots_txt": GuidanceSource(
        "Inleiding robots.txt",
        "https://developers.google.com/search/docs/crawling-indexing/robots/intro",
    ),
    "sitemap": GuidanceSource(
        "Een sitemap bouwen en indienen",
        "https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap",
    ),
    "title": GuidanceSource(
        "Title links beïnvloeden",
        "https://developers.google.com/search/docs/appearance/title-link",
    ),
    "snippet": GuidanceSource(
        "Snippets in zoekresultaten",
        "https://developers.google.com/search/docs/appearance/snippet",
    ),
    "links": GuidanceSource(
        "Best practices voor crawlbare links",
        "https://developers.google.com/search/docs/crawling-indexing/links-crawlable",
    ),
    "structured_data": GuidanceSource(
        "Inleiding structured data",
        "https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data",
    ),
    "breadcrumb": GuidanceSource(
        "Breadcrumb structured data",
        "https://developers.google.com/search/docs/appearance/structured-data/breadcrumb",
    ),
    "job_posting": GuidanceSource(
        "JobPosting structured data",
        "https://developers.google.com/search/docs/appearance/structured-data/job-posting",
    ),
    "helpful_content": GuidanceSource(
        "Nuttige, betrouwbare content maken",
        "https://developers.google.com/search/docs/fundamentals/creating-helpful-content",
    ),
    "image_alt": GuidanceSource(
        "Beslisboom voor alt-teksten",
        "https://www.w3.org/WAI/tutorials/images/decision-tree/",
        "W3C WAI",
    ),
    "performance": GuidanceSource(
        "Largest Contentful Paint optimaliseren",
        "https://web.dev/articles/optimize-lcp",
        "web.dev",
    ),
    "url_inspection": GuidanceSource(
        "Google URL Inspection API",
        "https://developers.google.com/webmaster-tools/v1/urlInspection.index/inspect",
    ),
}

SOURCE_KEYS_BY_TYPE = {
    "http_404": ("http",), "http_410": ("http",), "http_5xx": ("http",),
    "crawl_timeout": ("http",), "unreachable_url_target": ("http",),
    "redirect_loop": ("redirect",), "long_redirect_chain": ("redirect",),
    "internally_linked_redirect": ("redirect", "links"),
    "missing_title": ("title",), "duplicate_title": ("title",),
    "missing_h1": ("title",), "multiple_h1": ("title",),
    "missing_meta_description": ("snippet",), "duplicate_meta_description": ("snippet",),
    "canonical_other_url": ("canonical",), "duplicate_content": ("canonical",),
    "google_canonical_mismatch": ("url_inspection", "canonical"),
    "near_duplicate_content": ("canonical",), "conflicting_robots": ("robots",),
    "unexpected_noindex": ("robots",), "robots_txt_blocked": ("robots_txt",),
    "google_not_indexed": ("url_inspection",),
    "google_robots_blocked": ("url_inspection", "robots_txt"),
    "google_fetch_failed": ("url_inspection", "http"),
    "sitemap_redirect": ("sitemap", "redirect"), "sitemap_404": ("sitemap", "http"),
    "invalid_json_ld": ("structured_data",),
    "missing_breadcrumb_schema": ("breadcrumb",),
    "job_posting_schema_missing": ("job_posting",),
    "job_posting_missing_fields": ("job_posting",),
    "job_posting_invalid_dates": ("job_posting",),
    "job_posting_missing_application": ("job_posting",),
    "job_posting_remote_location_missing": ("job_posting",),
    "job_posting_location_incomplete": ("job_posting",),
    "job_posting_not_detail_page": ("job_posting",),
    "job_posting_identifier_collision_risk": ("job_posting",),
    "expired_job_posting": ("job_posting",),
    "expired_job_posting_linked": ("job_posting", "links"),
    "expired_job_posting_404": ("job_posting", "http"),
    "broken_application_cta": ("job_posting",),
    "internally_linked_404": ("links", "http"),
    "multiple_broken_internal_links": ("links", "http"),
    "multiple_redirected_internal_links": ("links", "redirect"),
    "patterned_404_urls": ("links", "http"),
    "pagination_series_review": ("canonical", "title", "snippet", "links"),
    "orphan_page": ("links",), "deep_page": ("links",),
    "image_alt_missing": ("image_alt",),
    "functional_image_alt_empty": ("image_alt",),
    "important_page_few_internal_links": ("links",),
    "generic_internal_anchor_text": ("links",),
    "downloadable_document_inventory": ("helpful_content", "performance"),
    "image_delivery_quality": ("image_alt", "performance"),
    "media_delivery_quality": ("performance", "helpful_content"),
    "cms_link_placeholder": ("links",),
    "thin_content": ("helpful_content",), "possibly_outdated_content": ("helpful_content",),
    "broken_image": ("helpful_content",),
    "oversized_image": ("performance",), "oversized_document": ("performance",),
    "template_signal_clusters": ("canonical", "title", "snippet", "links", "helpful_content"),
}


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
    "deep_page": (
        "Crawldiepte is alleen relevant wanneer een belangrijke pagina, een uitzonderlijk diepe "
        "route of een pagina met weinig interne ingangen wordt geraakt."
    ),
    "image_alt_missing": (
        "Een tekstalternatief maakt de inhoud of functie van een afbeelding beschikbaar voor "
        "hulptechnologie en geeft zoekmachines aanvullende beeldcontext."
    ),
    "functional_image_alt_empty": (
        "Een afbeelding die als link of knop werkt, moet een toegankelijke naam hebben zodat de "
        "bestemming of actie begrijpelijk blijft."
    ),
    "job_posting_schema_missing": (
        "Zonder JobPosting-schema kan Google deze vacature niet betrouwbaar als vacature herkennen."
    ),
    "multiple_broken_internal_links": (
        "Meerdere dode links onderbreken dezelfde gebruikersroute en verspillen crawlverkeer."
    ),
    "multiple_redirected_internal_links": (
        "Meerdere redirectlinks op één bronpagina zijn meestal één onderhoudstaak voor dezelfde "
        "pagina of hetzelfde gedeelde contentblok."
    ),
    "generic_internal_anchor_text": (
        "Beschrijvende linktekst geeft zoekmachines en gebruikers van hulptechnologie context "
        "over de bestemming voordat zij de link volgen."
    ),
    "downloadable_document_inventory": (
        "Belangrijke informatie in HTML is doorgaans beter bruikbaar, onderhoudbaar en te "
        "sturen in zoekresultaten dan een document als enige publicatievorm."
    ),
    "image_delivery_quality": (
        "Passende afmetingen en responsive bronnen beperken onnodige downloads en "
        "layoutverschuivingen."
    ),
    "media_delivery_quality": (
        "Goede media-opmaak ondersteunt laadtijd, toegankelijkheid en de herkenning van "
        "video-inhoud door zoekmachines."
    ),
    "internal_redirect_patterns": (
        "Herhaalde interne redirectdoelen met dezelfde URL-omzetting wijzen doorgaans op één "
        "navigatie-, component- of migratietaak."
    ),
    "patterned_404_urls": (
        "Een terugkerend 404-patroon wijst op structurele URL-generatie en kan veel "
        "ruis veroorzaken."
    ),
    "pagination_series_review": (
        "Een pagineringsreeks moet als één technisch geheel worden beoordeeld; losse metadata-, "
        "canonical- en dieptesignalen beschrijven meestal hetzelfde templategedrag."
    ),
    "sitemap_redirect_patterns": (
        "Een vast sitemapredirectpatroon is één configuratieprobleem in de sitemapgenerator, "
        "niet een afzonderlijke inhoudelijke fout op iedere URL."
    ),
    "server_error_incident": (
        "Gelijktijdige serverfouten kunnen één tijdelijk beschikbaarheidsincident zijn en moeten "
        "eerst gezamenlijk worden bevestigd."
    ),
    "template_signal_clusters": (
        "Herhaalde signalen binnen dezelfde URL-familie of metadatawaarde wijzen meestal op één "
        "template-, component- of contenttypebeslissing."
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
    "google_canonical_mismatch": (
        "Een nieuwe URL Inspection-observatie bevestigt de gewenste Google-selected canonical."
    ),
    "google_not_indexed": (
        "Een nieuwe URL Inspection-observatie bevestigt dat Google de bedoelde pagina indexeert."
    ),
    "google_robots_blocked": (
        "Google meldt na een nieuwe inspectie geen robots.txt-blokkade meer."
    ),
    "google_fetch_failed": (
        "Google meldt na een nieuwe inspectie een geslaagde page fetch."
    ),
    "conflicting_robots": (
        "Meta robots en X-Robots-Tag bevatten bij de volgende crawl geen conflict."
    ),
    "invalid_json_ld": "Alle JSON-LD-blokken zijn leesbaar en opnieuw gevalideerd.",
    "internally_linked_404": "Geen interne bronpagina linkt nog naar dit 404-doel.",
    "internally_linked_redirect": "Interne links wijzen rechtstreeks naar de definitieve 200-URL.",
    "image_alt_missing": (
        "De volgende crawl vindt op iedere betrokken inhoudelijke afbeelding een passend "
        "alt-attribuut."
    ),
    "functional_image_alt_empty": (
        "Iedere betrokken afbeeldingslink of -knop heeft een herkenbare toegankelijke naam."
    ),
    "internal_redirect_patterns": (
        "De volgende volledige crawl vindt geen interne links meer naar de betrokken "
        "redirect-URL's."
    ),
    "multiple_redirected_internal_links": (
        "Geen interne link op de bronpagina gaat nog via een redirect."
    ),
    "orphan_page": (
        "De pagina heeft een bewuste, crawlbare plek in de sitestructuur, of is samengevoegd of "
        "doorgestuurd naar de bedoelde bestemming en uit de sitemap verwijderd."
    ),
    "job_posting_schema_missing": (
        "De volgende crawl vindt geldig JobPosting-schema op de vacaturedetailpagina."
    ),
    "pagination_series_review": (
        "De volgende volledige crawl vindt alleen geldige reeks-URL's en geen lege grenspagina's."
    ),
    "sitemap_redirect_patterns": (
        "De volgende volledige crawl vindt de definitieve 200-URL's rechtstreeks in de sitemap."
    ),
    "server_error_incident": (
        "Een nieuwe light check geeft voor alle betrokken URL's een stabiele niet-5xx-status."
    ),
    "template_signal_clusters": (
        "De volgende volledige crawl werkt ieder aangepast cluster bij zonder dezelfde "
        "onbedoelde herhaling."
    ),
}


def build_issue_guidance(issue: Issue, evidence: dict[str, object]) -> dict[str, object]:
    guidance_type = (
        issue.issue_type
        if issue.issue_type == "template_signal_clusters"
        else issue.issue_type.removesuffix("_clusters")
    )
    relevance = TYPE_RELEVANCE.get(
        guidance_type,
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
            guidance_type,
            "Hetzelfde signaal is na een succesvolle volgende crawl niet meer aanwezig.",
        )
    )
    action = issue.recommended_action.strip()
    source_keys = SOURCE_KEYS_BY_TYPE.get(guidance_type, ())
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
        "sources": [
            {
                "title": SOURCES[key].title,
                "url": SOURCES[key].url,
                "publisher": SOURCES[key].publisher,
            }
            for key in source_keys
        ],
    }

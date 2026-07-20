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
    "performance": GuidanceSource(
        "Largest Contentful Paint optimaliseren",
        "https://web.dev/articles/optimize-lcp",
        "web.dev",
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
    "near_duplicate_content": ("canonical",), "conflicting_robots": ("robots",),
    "unexpected_noindex": ("robots",), "robots_txt_blocked": ("robots_txt",),
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
    "patterned_404_urls": ("links", "http"),
    "pagination_series_review": ("canonical", "title", "snippet", "links"),
    "orphan_page": ("links",), "deep_page": ("links",),
    "important_page_few_internal_links": ("links",),
    "cms_link_placeholder": ("links",),
    "thin_content": ("helpful_content",), "possibly_outdated_content": ("helpful_content",),
    "broken_image": ("helpful_content",),
    "oversized_image": ("performance",), "oversized_document": ("performance",),
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
    "pagination_series_review": (
        "Een pagineringsreeks moet als één technisch geheel worden beoordeeld; losse metadata-, "
        "canonical- en dieptesignalen beschrijven meestal hetzelfde templategedrag."
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
    "job_posting_schema_missing": (
        "De volgende crawl vindt geldig JobPosting-schema op de vacaturedetailpagina."
    ),
    "pagination_series_review": (
        "De volgende volledige crawl vindt alleen geldige reeks-URL's en geen lege grenspagina's."
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
    source_keys = SOURCE_KEYS_BY_TYPE.get(issue.issue_type, ())
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

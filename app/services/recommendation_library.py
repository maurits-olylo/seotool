from dataclasses import dataclass
from typing import Literal

RecommendationRole = Literal["content", "development", "seo_analytics", "project_management"]
RecommendationPriority = Literal["critical", "high", "normal", "low"]
Feasibility = Literal[
    "direct",
    "needs_content_input",
    "needs_technical_research",
    "needs_decision",
    "needs_manual_review",
]


@dataclass(frozen=True)
class RecommendationDefinition:
    key: str
    version: str
    source_issue_types: frozenset[str]
    title: str
    primary_role: RecommendationRole
    supporting_roles: tuple[RecommendationRole, ...]
    default_priority: RecommendationPriority
    effort_minutes: tuple[int, int] | None
    feasibility: Feasibility
    steps: tuple[str, ...]
    completion_criteria: tuple[str, ...]
    verification_scope: tuple[str, ...]


DEFINITIONS = (
    RecommendationDefinition(
        "repair_broken_internal_link",
        "2",
        frozenset({"internally_linked_404", "multiple_broken_internal_links"}),
        "Herstel defecte interne links",
        "content",
        ("seo_analytics",),
        "high",
        (10, 30),
        "direct",
        ("Open de bronpagina.", "Vervang of verwijder de defecte link.", "Publiceer de wijziging."),
        ("De bronlink is crawlbaar.", "Het doel retourneert 200 en is indexeerbaar."),
        ("source", "broken_target"),
    ),
    RecommendationDefinition(
        "replace_redirected_internal_link",
        "1",
        frozenset({"internally_linked_redirect", "multiple_redirected_internal_links"}),
        "Vervang interne redirects door eind-URL's",
        "content",
        ("development",),
        "normal",
        (10, 30),
        "direct",
        ("Open de bronpagina of het template.", "Vervang de link door de definitieve eind-URL."),
        ("De bron verwijst rechtstreeks naar een bereikbare eind-URL.",),
        ("source", "target"),
    ),
    RecommendationDefinition(
        "restore_or_redirect_missing_page",
        "1",
        frozenset({"http_404", "http_410", "sitemap_404"}),
        "Herstel of redirect een ontbrekende pagina",
        "development",
        ("seo_analytics", "content"),
        "high",
        (30, 120),
        "needs_decision",
        (
            "Bepaal of de pagina terugkomt of een opvolger heeft.",
            "Herstel of configureer de redirect.",
        ),
        (
            "De oude URL heeft de bedoelde status.",
            "Een eind-URL retourneert 200 indien van toepassing.",
        ),
        ("old", "new"),
    ),
    RecommendationDefinition(
        "resolve_server_or_fetch_failure",
        "1",
        frozenset({"http_5xx", "crawl_timeout", "server_error_incident"}),
        "Los server- of bereikbaarheidsfouten op",
        "development",
        (),
        "critical",
        None,
        "needs_technical_research",
        (
            "Reproduceer de fout.",
            "Controleer applicatie-, proxy- en serverlogs.",
            "Herstel de oorzaak.",
        ),
        ("De betrokken URL's reageren stabiel zonder 5xx of timeout.",),
        ("changed", "sample"),
    ),
    RecommendationDefinition(
        "fix_redirect_chain_or_loop",
        "2",
        frozenset({"redirect_loop", "long_redirect_chain"}),
        "Herstel redirectketen of redirectloop",
        "development",
        ("seo_analytics",),
        "high",
        (30, 120),
        "needs_technical_research",
        ("Breng de huidige redirectstappen in kaart.", "Maak een directe route naar de eind-URL."),
        ("Er is geen loop.", "De keten is direct en de eind-URL retourneert 200."),
        ("source", "expected_target"),
    ),
    RecommendationDefinition(
        "correct_indexability",
        "1",
        frozenset({"unexpected_noindex", "conflicting_robots", "robots_txt_blocked"}),
        "Corrigeer onverwachte indexatieblokkade",
        "seo_analytics",
        ("development",),
        "high",
        (30, 120),
        "needs_decision",
        ("Bevestig de bedoelde indexatiestatus.", "Pas robotsregels of pagina-instructies aan."),
        ("Robots-signalen zijn consistent.", "De pagina heeft de bedoelde indexeerbaarheid."),
        ("changed",),
    ),
    RecommendationDefinition(
        "correct_canonical",
        "2",
        frozenset({"canonical_other_url", "canonical_other_url_clusters"}),
        "Corrigeer de canonical",
        "development",
        ("seo_analytics",),
        "high",
        (20, 120),
        "needs_decision",
        ("Bevestig de voorkeurs-URL.", "Pas de canonical in pagina of template aan."),
        (
            "De bron bevat één bedoelde canonical.",
            "Het canonical-doel is bereikbaar en indexeerbaar.",
        ),
        ("source", "expected_canonical"),
    ),
    RecommendationDefinition(
        "add_or_correct_title",
        "1",
        frozenset({"missing_title", "duplicate_title", "duplicate_title_clusters"}),
        "Voeg een unieke, passende paginatitel toe",
        "content",
        ("seo_analytics",),
        "normal",
        (10, 30),
        "needs_content_input",
        ("Bepaal de primaire paginafunctie.", "Schrijf en publiceer een onderscheidende title."),
        ("De title bestaat en is uniek binnen de gecontroleerde scope.",),
        ("changed", "sample"),
    ),
    RecommendationDefinition(
        "add_primary_heading",
        "1",
        frozenset({"missing_h1", "multiple_h1", "missing_h1_clusters", "multiple_h1_clusters"}),
        "Corrigeer de primaire paginakop",
        "content",
        ("development",),
        "normal",
        (10, 30),
        "needs_content_input",
        ("Bepaal de primaire paginakop.", "Voeg één duidelijke H1 toe of corrigeer het template."),
        ("De bedoelde H1 is zichtbaar.", "De kopstructuur bevat geen onverwachte extra H1."),
        ("changed", "sample"),
    ),
    RecommendationDefinition(
        "add_meta_description",
        "1",
        frozenset(
            {
                "missing_meta_description",
                "duplicate_meta_description",
                "missing_meta_description_clusters",
                "duplicate_meta_description_clusters",
            }
        ),
        "Voeg een passende meta description toe",
        "content",
        ("seo_analytics",),
        "low",
        (10, 30),
        "needs_content_input",
        ("Schrijf een paginaspecifieke omschrijving.", "Publiceer deze in het CMS of template."),
        ("De description bestaat en is uniek binnen de gecontroleerde scope.",),
        ("changed", "sample"),
    ),
    RecommendationDefinition(
        "repair_structured_data",
        "1",
        frozenset({"invalid_json_ld", "missing_breadcrumb_schema"}),
        "Herstel structured data",
        "development",
        ("seo_analytics",),
        "normal",
        (30, 120),
        "needs_technical_research",
        ("Identificeer het ongeldige of ontbrekende schema.", "Pas de markup of generator aan."),
        ("JSON-LD is technisch geldig.", "De bedoelde schematypen zijn aanwezig."),
        ("changed", "sample"),
    ),
    RecommendationDefinition(
        "repair_job_posting_markup",
        "1",
        frozenset(
            {
                "expired_job_posting",
                "expired_job_posting_linked",
                "expired_job_posting_404",
                "job_posting_schema_missing",
                "job_posting_missing_fields",
                "job_posting_invalid_dates",
                "job_posting_remote_location_missing",
                "job_posting_location_incomplete",
            }
        ),
        "Herstel JobPosting-markup of vacaturestatus",
        "development",
        ("content", "seo_analytics"),
        "high",
        (30, 120),
        "needs_content_input",
        ("Controleer vacaturestatus en vereiste velden.", "Werk pagina en schema consistent bij."),
        ("De vacaturestatus klopt.", "JobPosting-markup is geldig en consistent met de pagina."),
        ("changed", "sample"),
    ),
    RecommendationDefinition(
        "repair_application_action",
        "1",
        frozenset({"broken_application_cta", "job_posting_missing_application"}),
        "Herstel de sollicitatieactie",
        "development",
        ("content",),
        "high",
        (15, 60),
        "direct",
        ("Open de vacature en test de CTA.", "Koppel de knop aan het werkende formulier of doel."),
        ("De sollicitatieactie is zichtbaar, bruikbaar en heeft een werkende bestemming.",),
        ("source", "target"),
    ),
    RecommendationDefinition(
        "replace_cms_link_placeholder",
        "1",
        frozenset({"cms_link_placeholder", "cms_link_placeholder_clusters"}),
        "Vervang de onverwerkte CMS-link",
        "content",
        ("development",),
        "high",
        (10, 30),
        "direct",
        (
            "Open het betrokken contentblok of template.",
            "Vervang de placeholder door de juiste URL.",
        ),
        ("De placeholder is verdwenen.", "De nieuwe link is crawlbaar en bereikbaar."),
        ("source", "target"),
    ),
    RecommendationDefinition(
        "connect_orphan_page",
        "1",
        frozenset(
            {
                "orphan_page",
                "orphan_page_clusters",
                "important_page_few_internal_links",
            }
        ),
        "Verbind de pagina met relevante interne links",
        "seo_analytics",
        ("content",),
        "normal",
        (20, 90),
        "needs_manual_review",
        ("Selecteer relevante bronpagina's.", "Voeg contextuele links naar de doelpagina toe."),
        ("De doelpagina heeft relevante crawlbare inkomende links.",),
        ("source", "target"),
    ),
)

DEFINITIONS_BY_KEY = {definition.key: definition for definition in DEFINITIONS}
DEFINITION_BY_ISSUE_TYPE = {
    issue_type: definition
    for definition in DEFINITIONS
    for issue_type in definition.source_issue_types
}

if len(DEFINITIONS_BY_KEY) != len(DEFINITIONS):
    raise RuntimeError("Recommendation definition keys must be unique")
if sum(len(item.source_issue_types) for item in DEFINITIONS) != len(DEFINITION_BY_ISSUE_TYPE):
    raise RuntimeError("An issue type can map to only one recommendation definition")


def get_recommendation_definition(key: str) -> RecommendationDefinition:
    try:
        return DEFINITIONS_BY_KEY[key]
    except KeyError as exc:
        raise KeyError(f"Unknown recommendation type: {key}") from exc


def recommendation_for_issue_type(issue_type: str) -> RecommendationDefinition | None:
    return DEFINITION_BY_ISSUE_TYPE.get(issue_type)

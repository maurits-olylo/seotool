"""Specific next steps for the bounded, read-only work pilot."""

from datetime import UTC, datetime, timedelta
from typing import Any

# These require a site comparison, not just a later download of one page.
SITE_EVIDENCE = {
    "orphan_page",
    "sitemap_404",
    "duplicate_title",
    "duplicate_meta_description",
    "duplicate_content",
    "internally_linked_404",
    "internally_linked_redirect",
    "multiple_broken_internal_links",
    "multiple_redirected_internal_links",
}
HTTP_EVIDENCE = {"http_404", "http_410", "http_5xx"}


def evidence_state(
    kind: str,
    occurrence: Any,
    measured: Any,
    analyzed: Any,
    runs: dict,
    latest_full: Any,
    now: datetime,
    *,
    flags: dict | None = None,
) -> tuple[bool, str, str]:
    """Keep full-analysis evidence through light checks; never certify missing routes."""
    if not occurrence:
        return False, "missing_observation", "Een opgeslagen bewijswaarneming ontbreekt."
    run = runs.get(occurrence.crawl_run_id)
    if not run or run.status not in {"succeeded", "partially_succeeded"}:
        return False, "unfinished_source", "De bronmeting is niet succesvol afgerond."
    moment = occurrence.detected_at
    if moment.replace(tzinfo=UTC) > now or moment.replace(tzinfo=UTC) < now - timedelta(days=7):
        return (
            False,
            "old_observation",
            "De bewijswaarneming valt buiten de proeftermijn van zeven dagen.",
        )
    if kind in SITE_EVIDENCE:
        if not latest_full or latest_full.id != run.id:
            return (
                False,
                "site_comparison_needed",
                (
                    "Vergelijk dit signaal met de nieuwste volledige siteanalyse. Een "
                    "light check bewijst de sitestructuur niet."
                ),
            )
        # A snapshot-less contextual signal is a valid observation, but not enough to
        # declare its status/route independently confirmed or to release execution.
        if not occurrence.snapshot_id:
            return (
                False,
                "site_evidence_needed",
                (
                    "De sitewaarneming is recent, maar het gekoppelde pagina- of "
                    "routebewijs ontbreekt."
                ),
            )
    if kind == "orphan_page" and (flags or {}).get("root_route_checked") is not True:
        return (
            False,
            "route_proof_needed",
            ("De waarneming bevat geen expliciet bewijs van een controle vanaf de homepage."),
        )
    if (
        kind == "structured_data_visible_content_mismatch"
        and (flags or {}).get("comparison_version") != 3
    ):
        return (
            False,
            "schema_recheck_needed",
            (
                "Dit bewijs is niet met de huidige schemavergelijking beoordeeld. "
                "Laat eerst opnieuw analyseren."
            ),
        )
    relevant = measured if kind in HTTP_EVIDENCE | {"sitemap_404"} else analyzed
    if not relevant or relevant.id != occurrence.snapshot_id:
        return (
            False,
            "analysis_needed",
            (
                "De passende analyse ontbreekt of is nieuwer dan het bewijs bij dit "
                "signaal. Controleer de inhoudelijke onderbouwing opnieuw."
            ),
        )
    if relevant.error_message or relevant.status_code is None:
        return (
            False,
            "failed_page_measurement",
            "De passende paginameting bevat geen bruikbaar HTTP-resultaat.",
        )
    if relevant.checked_at.replace(tzinfo=UTC) < now - timedelta(days=7):
        return (
            False,
            "old_analysis",
            (
                "De passende analyse is ouder dan zeven dagen; een recentere light "
                "check vernieuwt dit bewijs niet."
            ),
        )
    if (
        measured
        and measured.id != relevant.id
        and (
            measured.error_message
            or measured.status_code != relevant.status_code
            or measured.final_url != relevant.final_url
        )
    ):
        return (
            False,
            "changed_reachability",
            (
                "De nieuwste paginacontrole wijkt af in bereikbaarheid of bestemming."
                " Controleer dit vóór inhoudelijk werk."
            ),
        )
    return (
        True,
        "aligned",
        (
            "Het signaal sluit aan op de passende opgeslagen analyse; dit is geen"
            " nieuwe live controle."
        ),
    )


def next_step(kind: str) -> tuple[str, str, str]:
    if kind in {"duplicate_title", "duplicate_meta_description", "duplicate_content"}:
        return (
            (
                "Vergelijk deze pagina met de genoemde andere pagina’s. Bepaal per "
                "pagina de doelgroep, zoekvraag en eigen functie; kies daarna "
                "behouden met onderscheidende inhoud of samenvoegen."
            ),
            "Inhoudelijk verantwoordelijke / SEO-manager",
            (
                "Per pagina zijn de functie en het besluit vastgelegd. Bij behoud "
                "krijgt de redactie een concrete schrijfopdracht; bij samenvoegen "
                "krijgt de webbouwer de gekozen bestemming."
            ),
        )
    if kind == "orphan_page":
        return (
            (
                "Controleer bij Bronnen de bekende inkomende links en volg de route "
                "vanaf de homepage. Leg vast welke schakel ontbreekt of onzeker is. "
                "Laat daarna de inhoudelijk verantwoordelijke bepalen of deze pagina "
                "zelfstandig moet blijven."
            ),
            "SEO-manager",
            (
                "Een route vanaf de homepage is aangetoond, of de ontbrekende schakel"
                " en het besluit over behoud zijn vastgelegd. Pas daarna wordt een "
                "link- of redirectopdracht bepaald."
            ),
        )
    if kind in {"sitemap_404", "http_404", "http_410"}:
        return (
            (
                "Vergelijk de laatste HTTP-status met de actuele sitemapvermelding. "
                "Laat de inhoudelijk verantwoordelijke bepalen of de pagina nog nodig"
                " is, definitief vervalt of een inhoudelijke opvolger heeft."
            ),
            "SEO-manager → inhoudelijk verantwoordelijke",
            (
                "Status en sitemap zijn gecontroleerd en het besluit is vastgelegd. "
                "Daarna kan de webbouwer gericht herstellen, de sitemap aanpassen of "
                "naar de gekozen opvolger verwijzen."
            ),
        )
    if kind == "structured_data_visible_content_mismatch":
        return (
            (
                "Controleer het genoemde schematype, veld en de zichtbare inhoud. "
                "Bepaal of de entiteit het onderwerp van de pagina is: een "
                "organisatienaam hoeft niet gelijk te zijn aan de paginatitel. Pas "
                "alleen een aangetoonde afwijking aan."
            ),
            "SEO-manager, daarna zo nodig webbouwer",
            (
                "De vergelijking is inhoudelijk bevestigd of als niet van toepassing "
                "onderbouwd. Alleen bij een echte afwijking krijgt de webbouwer het "
                "exacte veld en de juiste waarde."
            ),
        )
    if kind in {
        "internally_linked_404",
        "multiple_broken_internal_links",
        "internally_linked_redirect",
        "multiple_redirected_internal_links",
    }:
        return (
            (
                "Open de bronpagina’s en controleer per link de bestemming en "
                "bedoeling. Kies met de inhoudelijk verantwoordelijke een passende "
                "bestemming of verwijdering voordat de redactie de links wijzigt."
            ),
            "SEO-manager → redactie",
            (
                "Per bronlink is een bestemming of verwijdering afgesproken; na "
                "uitvoering zijn de aangepaste links en bestemmingen gecontroleerd."
            ),
        )
    return (
        (
            "Controleer het genoemde onderdeel op de pagina en leg de gewenste "
            "wijziging vast voordat een opdracht wordt verstrekt."
        ),
        "SEO-manager",
        ("Het bewijs, de gewenste wijziging en de verantwoordelijke zijn vastgelegd."),
    )


def evidence_facts(kind: str, data: dict) -> list[str]:
    """Allowlisted, bounded facts, never raw HTML or arbitrary evidence dumps."""
    facts = []
    if not isinstance(data, dict):
        return facts
    if kind.startswith("duplicate_"):
        if data.get("value"):
            facts.append("Gemeten gedeelde waarde: " + str(data["value"])[:600])
        for url in (data.get("related_urls") or [])[:5]:
            facts.append("Andere pagina: " + str(url)[:2048])
    if kind == "sitemap_404" and data.get("in_sitemap") is True:
        facts.append(
            "De bewijswaarneming registreert een sitemapvermelding; controleer "
            "daarnaast de HTTP-status."
        )
    if kind == "orphan_page":
        facts.append(
            "Route vanaf homepage gecontroleerd: "
            + ("ja" if data.get("root_route_checked") is True else "niet vastgelegd in dit bewijs")
        )
    if kind == "structured_data_visible_content_mismatch":
        for item in (data.get("mismatches") or [])[:5]:
            if isinstance(item, dict):
                facts.append(
                    f"{str(item.get('schema_type', 'Onbekend type'))[:80]} · "
                    f"{str(item.get('field', 'onbekend veld'))[:80]}: "
                    f"{str(item.get('schema_value', 'waarde ontbreekt'))[:300]}"
                )
        if data.get("comparison_version") != 3:
            facts.append(
                "Bewijs komt niet uit de huidige schemavergelijking; laat eerst "
                "opnieuw analyseren vóór een wijzigingsopdracht."
            )
    return facts

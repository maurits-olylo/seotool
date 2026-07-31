# Taakgerichte aanbevelingen — MVP-ontwerp

## Doel en afbakening

De eerste versie maakt bestaande diagnoses uitvoerbaar zonder de automatische issue-lifecycle te
vermengen met menselijke taakuitvoering. Een issue blijft technisch bewijs en kan automatisch
`resolved`, `verified` of opnieuw geopend worden. Een gekoppelde taak bewaart eigenaar, planning,
uitvoering, feedback en verificatie.

Niet in de eerste versie:

- automatisch publiceren;
- externe projectmanagement- of notificatiekoppelingen;
- CMS-specifieke instructies;
- AI als bron voor diagnose, prioriteit of verificatie;
- klantoverstijgend leren op ruwe content, URL's, queries of analyticsregels;
- automatische inhoudelijke, juridische of ontwerpgoedkeuring.

## Rollen en statussen

Iedere taak heeft precies één primaire rol:

- `content`;
- `development`;
- `seo_analytics`;
- `project_management`.

Ondersteunende rollen gebruiken dezelfde vier waarden. UX/UI-werk valt in de MVP onder
`development` of `content`, afhankelijk van de wijziging. Een fijnere rolverdeling volgt alleen
wanneer productiegebruik daar behoefte aan toont.

Menselijke taakstatus:

- `open`;
- `planned`;
- `in_progress`;
- `waiting_for_input`;
- `implemented`;
- `closed`.

Een gesloten taak bewaart daarnaast een reden: `verified`, `manually_accepted`, `rejected`,
`superseded` of `no_longer_relevant`.

Verificatiestatus blijft afzonderlijk:

- `not_requested`;
- `queued`;
- `running`;
- `passed`;
- `likely_passed`;
- `manual_review`;
- `failed`;
- `error`;
- `cancelled`.

Hierdoor kan een taak `implemented` zijn terwijl technische controle nog loopt of menselijke
inhoudscontrole nodig blijft.

## Eerste aanbevelingsbibliotheek

De bibliotheek is versieerbare applicatieconfiguratie. Databaseversies bewaren welke definitie
voor een taak is gebruikt. De eerste selectie bevat alleen veelvoorkomende, concrete en grotendeels
controleerbare acties.

| Aanbevelingstype | Bronsignalen | Primaire rol | Eerste verificatiescope |
|---|---|---|---|
| `repair_broken_internal_link` | `internally_linked_404`, bronclusters | `content` | bron en doel |
| `replace_redirected_internal_link` | `internally_linked_redirect`, bronclusters | `content` | bron en einddoel |
| `restore_or_redirect_missing_page` | `http_404`, `http_410`, `sitemap_404` | `development` | oude en bedoelde URL |
| `resolve_server_or_fetch_failure` | `http_5xx`, `crawl_timeout`, incidentcluster | `development` | betrokken URL of steekproef |
| `fix_redirect_chain_or_loop` | `redirect_loop`, `long_redirect_chain` | `development` | begin- en eind-URL |
| `correct_indexability` | `unexpected_noindex`, `conflicting_robots`, `robots_txt_blocked` | `seo_analytics` | URL plus robotscontext |
| `correct_canonical` | `canonical_other_url`, canonicalcluster | `development` | bron, doel en variant |
| `add_or_correct_title` | `missing_title`, `duplicate_title` | `content` | URL of templatesteekproef |
| `add_primary_heading` | `missing_h1`, `multiple_h1` | `content` | URL of templatesteekproef |
| `add_meta_description` | `missing_meta_description`, `duplicate_meta_description` | `content` | URL of templatesteekproef |
| `repair_structured_data` | `invalid_json_ld`, contextuele schemacontroles | `development` | URL of templatesteekproef |
| `repair_job_posting_markup` | harde JobPosting-signalen en clusters | `development` | vacature of steekproef |
| `repair_application_action` | `broken_application_cta`, ontbrekende sollicitatieactie | `development` | vacature en formulierdoel |
| `replace_cms_link_placeholder` | `cms_link_placeholder` | `content` | bron en doel |
| `resolve_orphan_structure` | `orphan_page` en orphanclusters | `seo_analytics` | besluit: structureel opnemen of samenvoegen/redirecten |
| `connect_orphan_page` | belangrijke pagina met te weinig interne links | `seo_analytics` | relevante bronpagina's en linkcontext |

`thin_content`, `near_duplicate_content`, algemene ouderdom, alt-tekstoptimalisatie,
zoekintentie, samenvoegen, splitsen en noindex blijven eerst review- of analysetaken. Ze zijn te
contextafhankelijk voor automatische gereedverklaring.

## Voorgesteld datamodel

Definitieve namen worden tijdens implementatie aan de bestaande conventies getoetst.

### `recommendation_tasks`

- UUID, website-ID en aanmaker;
- recommendation type en definitieversie;
- titel, probleemcategorie en primaire issue-ID;
- menselijke status en sluitreden;
- primaire en ondersteunende rollen;
- prioriteit plus tekstuele onderbouwing;
- tijdsbandbreedte en confidence;
- uitvoerbaarheidsniveau;
- wat, waarom, stappen, afhankelijkheden, benodigde input en gereedcriteria;
- verificatiespecificatie en verificatiestatus;
- aangemaakt, gewijzigd, uitgevoerd en gesloten in UTC.

### `recommendation_task_issues`

Koppelt één taak aan één of meer onderliggende issues. De issuehistorie blijft de bron voor
diagnosebewijs; bewijs wordt niet naar de taak gekopieerd.

### `recommendation_task_urls`

Bewaar per taak de betrokken URL-ID en een aanbevelingsspecifieke rol. Voor de eerste gerichte
controles zijn dat `source` en `broken_target`, `source` en `expected_target`, of `source` en
`expected_canonical`. De taakcreatie vult bekende rollen automatisch uit issuebewijs, linkgraaf en
snapshot. Bevoegde gebruikers kunnen ontbrekende rollen binnen de ingestelde websitescope
toevoegen of verwijderen; deze correcties zijn auditbaar.

### `recommendation_task_events`

Onveranderlijke historie met actor, gebeurtenistype, vorige en nieuwe status, toelichting,
verificatiekeuze en tijdstip. Dit vult `activity_log` aan met taakdetails; het globale activity log
kan een compacte verwijzing blijven tonen.

### `recommendation_verifications`

Bewaar job-ID, scopeversie, voor- en nasnapshots, uitgevoerde regels, voortgang, uitkomst,
foutdetails en timestamps. Verificaties gebruiken een eigen jobtype op de lichte crawlqueue en
verversen de wekelijkse full-crawlplanning niet.

Implementatiestatus: tabel, tenantbeveiligde lees-API, scopeplan, automatische bewijsverrijking en
beveiligde handmatige scopecorrectie zijn gereed. De eerste scope omvat defecte interne links,
redirectketens/-loops en canonicals. Enqueueing blijft uitgeschakeld totdat de dedicated executor
uitsluitend de vastgelegde URL-ID's verwerkt; de algemene light check mag hiervoor niet worden
gebruikt.

### `recommendation_feedback`

Klantgebonden feedback:

- werkelijke tijd als band en optioneel minuten;
- ervaren moeilijkheid;
- ontbrekende input of afhankelijkheid;
- instructie bruikbaar ja/nee;
- handmatige correctie en reden;
- afwijsreden;
- technische verificatie-uitkomst;
- menselijke eindbeoordeling.

Implementatiestatus: de eerste API- en interfaceversie registreert werkelijke minuten met
automatisch afgeleide tijdsband, moeilijkheid, bruikbaarheid, ontbrekende input of afhankelijkheid,
eindbeoordeling en optionele klantgebonden toelichting. Feedback is append-only en pas beschikbaar
na uitvoering of afsluiting. Correctie-, afwijs- en verificatievelden worden geactiveerd samen met
hun eigen workflows.

## Statusovergangen

- `open` → `planned`, `in_progress` of `closed`;
- `planned` → `in_progress`, `waiting_for_input` of `closed`;
- `in_progress` → `waiting_for_input`, `implemented` of `closed`;
- `waiting_for_input` → `planned`, `in_progress` of `closed`;
- `implemented` → `in_progress` bij herstelwerk of `closed` na verificatie/beoordeling;
- `closed` kan alleen via expliciet heropenen terug naar `open`.

Het markeren als `implemented` maakt na bevestiging van aangepaste URL's een gerichte
verificatiejob. Een mislukte verificatie verandert de taak niet stilzwijgend terug; zij krijgt
`failed` en vraagt een bewuste vervolgactie.

## Privacyveilige kalibratie over klanten

De eerste releases verzamelen alleen klantgebonden feedback. Een latere aggregatiejob maakt
uitsluitend statistieken wanneer alle privacyvoorwaarden zijn gehaald:

- minimaal 10 onafhankelijke klanten;
- minimaal 50 beoordeelde taken per aggregatiecel;
- geen klant draagt meer dan 20% van een cel bij; bijdragen worden anders begrensd;
- segmenten gebruiken alleen recommendation type en voldoende brede sector-, CMS- en schaalbakken;
- kleine of herleidbare cellen worden niet gepubliceerd of toegepast;
- medianen en brede percentielen voor tijd, geen individuele waarden;
- uitkomstpercentages krijgen betrouwbaarheidsinterval en modelversie;
- verwijdering of uitsluiting van een klant kan aggregaten opnieuw laten opbouwen;
- deelname en grondslag worden vóór activering juridisch en contractueel vastgesteld.

Nooit klantoverstijgend verwerken:

- ruwe pagina-inhoud, URL's, domeinen of anchors;
- zoekopdrachten en individuele analyticsregels;
- klant-, gebruikers- of concurrentie-identiteiten;
- vrije opmerkingen zonder afzonderlijke anonimisering.

Eerste toepassingen:

1. effort-banden kalibreren;
2. confidence vergelijken met verificatie- en correctie-uitkomsten;
3. aanbevelingstypen met veel afwijzingen of handmatige correcties terugzetten naar review;
4. verificatieregels evalueren op foutpositieven en onduidelijke uitkomsten.

Aggregaten wijzigen nooit autonoom productiegedrag. Een nieuwe regel- of calibratieversie wordt
eerst offline geëvalueerd, expliciet goedgekeurd, versioneerbaar uitgerold en terugdraaibaar
gehouden.

## Implementatievolgorde en raming

1. Bibliotheek, taak-/eventmodel en autorisatie: 4–6 werkdagen.
2. API en eenvoudige taak-/analyseweergave: 5–7 werkdagen.
3. Feedback, activity log en eerste productievalidatie: 3–5 werkdagen.
4. Gerichte verificatie voor zes objectieve typen: 7–10 werkdagen.
5. Voortgang, retries en in-app voltooiingsmelding: 3–5 werkdagen.

Lean MVP: circa 3–4 weken. Volledige eerste verificatieversie: circa 5–7 weken. De latere
klantoverstijgende aggregatie kost naar verwachting 2–4 weken, maar wordt pas geactiveerd wanneer
voldoende onafhankelijke productiegegevens bestaan.

## Acceptatie vóór implementatiestart

- De producteigenaar keurt rollen, taakstatussen, sluitredenen en MVP-aanbevelingstypen goed.
- Iedere definitie heeft concrete benodigde input, stappen, gereedcriteria en verificatiescope.
- Tenantautorisatie geldt voor taken, events, URL's, verificaties en feedback.
- Geen issuebewijs wordt gedupliceerd of door taakstatus overschreven.
- Aggregatie blijft technisch uitgeschakeld totdat privacy-, volume- en evaluatievoorwaarden zijn
  goedgekeurd.

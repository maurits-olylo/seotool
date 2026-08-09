# Release 12 — Continuous Website Improvement-pilot

Status: volledig lokaal, op staging en in productie geaccepteerd.

## Doel en afbakening

Release 12 gebruikt accessibility als eerste extra kwaliteitsbron binnen dezelfde verbetercyclus
als SEO-signalen. De release bouwt geen WCAG-score, certificering, apart dashboard of generieke
rules engine. Het ontwerp staat in `docs/continuous-website-improvement-design.md`.

## Fase A — architectuur

Status: afgerond.

De bestaande keten `signaal → issue → taak → verificatie → interventie → effect` blijft
leidend. Accessibility is een bron en bewijsdomein binnen die keten.

## Fase B — accessibility-fundament

Status: lokaal en op staging geïmplementeerd en getest.

- axe-core `4.12.1` wordt lokaal in de renderimage opgenomen; er is geen CDN- of runtime-download;
- analyse draait optioneel in dezelfde Playwright-pagina en alleen bij een expliciet aangevraagde
  accessibility-waarneming;
- de pilot beperkt zich tot tien regels voor namen, labels, taal, titel, kopstructuur en ARIA;
- maximaal honderd gevonden nodes per pagina en tien bewijsnodes per regel worden verwerkt;
- `violations` worden genormaliseerd naar bestaande issues met categorie `accessibility`;
- `incomplete` blijft apart bewaard bewijs en wordt niet automatisch een hard issue;
- engineversie, WCAG-tags, selector, beperkt HTML-bewijs en herstelcontext blijven uitlegbaar;
- er is geen databasemigratie nodig: resultaten landen in `RenderObservation.comparison` en
  `IssueOccurrence.evidence`.

## Lokale acceptatie fase B

- gerichte accessibility-, renderer- en executortests: 14 geslaagd;
- volledige testsuite: 553 geslaagd, alleen de bestaande Starlette/httpx-waarschuwing;
- Ruff en diffcontrole: geslaagd;
- lokale imagebuild: niet uitgevoerd omdat de Docker-engine niet actief was;
- stagingimagebuild: geslaagd vanaf hotfixcommit `4611bf2`;
- de eerste stagingproef vond een CSP-conflict bij injectie via `add_script_tag`; axe wordt daarom
  vóór navigatie als Playwright-initscript geladen zonder de pagina-CSP te wijzigen;
- de herhaalde synthetische browserproef bevestigde axe-core `4.12.1`, tien pilotregels, een gezonde
  renderworker en een gezonde API en database;
- gereedsignaal: `release-12-phase-b-staging-ok`.

## Volgende fase

## Fase C — grouping en workflow

Status: lokaal en op staging geïmplementeerd en integraal geaccepteerd.

- ieder hard accessibilityissue bewaart een deterministische componenthandtekening op basis van
  regel en begrensde selector;
- positionele selectorindexen worden genormaliseerd, zodat hetzelfde gedeelde component over
  meerdere pagina's herkenbaar blijft;
- taakcreatie koppelt maximaal vijftig actieve issues met dezelfde regel, componenthandtekening en
  website aan één bestaande `RecommendationTask`;
- iedere betrokken URL krijgt de rol `changed`; een andere component of tenant wordt nooit
  stilzwijgend toegevoegd;
- de bestaande automatische overgang naar `implemented` plant de hercontrole op de renderqueue;
- iedere voorbeeldpagina krijgt een historische `RenderObservation` met axe-resultaat;
- alleen wanneer de oorspronkelijke regel op alle voorbeelden verdwenen is, sluit de taak als
  geverifieerd en kan de bestaande effectmeting starten;
- een blijvende overtreding brengt de taak terug naar `in_progress`; een later terugkerende
  overtreding heropent het bestaande issue als regressie zonder duplicaat.
- de herbruikbare stagingfixture gebruikt twee synthetische, klantvrije pagina's met hetzelfde
  component en controleert bundeling, herstel, twee renderwaarnemingen en automatische sluiting.

Lokale acceptatie:

- componentnormalisatie, multi-issue bundeling, tenantscope, renderqueuekeuze, positieve
  hercontrole en regressie zijn geautomatiseerd getest;
- volledige regressiesuite: 556 geslaagd, alleen de bestaande Starlette/httpx-waarschuwing;
- Ruff en diffcontrole: geslaagd.

Eerste stagingpoging:

- API en renderworker zijn vanaf fixturecommit `074bd82` herbouwd en gezond gestart;
- de fixture stopte terecht voordat klantvrije testdata werd verwerkt, omdat de renderworker geen
  algemene API-key bevat;
- de fixture wordt gecorrigeerd naar vaste herstelde live pagina's en heeft daardoor geen secret of
  muterende API-aanroep meer nodig;
- fase C is pas geaccepteerd nadat de volledige fixture alsnog slaagt.

Tweede stagingpoging:

- beide axe-renderwaarnemingen slaagden;
- de verificatie stopte bij effectmaterialisatie doordat het versieerbare crawlerrollenbeleid geen
  rechten op de in Release 10 toegevoegde effecttabellen bevatte;
- het rollenbeleid krijgt alleen de noodzakelijke leesrechten op effectbronnen en lees-/invoegrecht
  op `effect_interventions` en `effect_evaluations`;
- de fixture ruimt een eerder afgebroken synthetische taak op voordat zij opnieuw begint;
- fase C blijft onbevestigd totdat rollenconfiguratie en de volledige fixture slagen.

Derde stagingpoging:

- de rollenconfiguratie is toegepast en de services zijn gezond;
- de herhaalcleanup gebruikte ten onrechte `DISTINCT` op een volledig taakrecord met JSON-kolommen,
  wat PostgreSQL niet ondersteunt;
- de cleanup selecteert voortaan eerst unieke taak-ID's en laadt daarna de taken zonder vergelijking
  van JSON-waarden;
- een statische regressietest bewaakt dat de fixture geen `DISTINCT` op taakrecords herintroduceert.

Definitieve stagingacceptatie:

- API, database, Redis en renderworker waren gezond;
- twee synthetische issues met dezelfde componenthandtekening zijn tot één taak gebundeld;
- axe-core heeft beide herstelde pagina's opnieuw gecontroleerd en twee historische
  renderwaarnemingen opgeslagen;
- verificatie `bec1fe36-fd78-4b99-83b0-c3b82af0d1de` is geslaagd en de taak is automatisch
  afgehandeld;
- API en database bleven na de volledige workflow gezond;
- gereedsignaal: `release-12-phase-c-staging-ok`.

## Fase D — uitlegbare cross-domainprioritering

Status: lokaal en op staging geïmplementeerd en geaccepteerd.

- de bestaande kansberekening blijft intern beschikbaar voor reproduceerbare sortering, maar de
  interface toont geen universele `/100`-score meer;
- iedere kans legt prioriteit uit via impactdomeinen, bereik, bewijs, uitvoerbaarheid, urgentie en
  businesscontext;
- ontbrekend bewijs verlaagt de zekerheid zonder een aantoonbaar probleem te verbergen;
- een belangrijke pagina met een hard accessibilityissue kan ook zonder zoekprestatiegegevens als
  cross-domainkans worden opgenomen;
- bronlabels in de gebruikersinterface zijn functioneel en noemen geen externe leverancier;
- bestaande SEO-kansen gebruiken dezelfde factorgerichte uitleg, zodat geen tweede workflow of
  apart accessibilitydashboard ontstaat.

Acceptatie vereist minimaal een kans met gecombineerde SEO- en accessibilityimpact, een kandidaat
zonder zoekdata, een bestaande SEO-kans met dezelfde uitlegstructuur en een controle dat de UI geen
algemene score of leveranciersnaam toont.

Lokale acceptatie:

- belangrijke accessibilitypagina zonder zoekdata en bestaande SEO-kansen: geautomatiseerd getest;
- gebruikersinterface toont factorgerichte prioriteit en functionele bronlabels zonder `/100`-score;
- volledige regressiesuite: 558 geslaagd, alleen de bestaande Starlette/httpx-waarschuwing;
- Ruff, JavaScript-syntax en diffcontrole: geslaagd.

Stagingacceptatie:

- de API, PostgreSQL en Redis waren gezond en migratie `0060` stond op head;
- een belangrijke synthetische pagina leverde zonder zoekprestatiegegevens een cross-domainkans
  met SEO- en accessibilityimpact op;
- een bestaande synthetische SEO-kans gebruikte dezelfde factorgerichte uitlegstructuur;
- ontbrekend zoekbewijs bleef zichtbaar als onzekerheidsfactor en blokkeerde de aantoonbare kans
  niet;
- de interfacecontrole bevestigde functionele bronlabels en de afwezigheid van een algemene
  `/100`-score;
- gereedsignaal: `release-12-phase-d-staging-ok`.

De eerste visuele controle bevestigde de kaarten en prioriteit, maar vond in de uitgeklapte uitleg
nog interne waarden voor uitvoerbaarheid, urgentie en businesscontext. De interface vertaalt deze
waarden voortaan naar begrijpelijke Nederlandse tekst en toont geen ruwe JSON. De herbouwde
staginginterface is daarna opnieuw gecontroleerd: beide kansen werden correct getoond, de
cross-domainuitleg bevatte uitsluitend begrijpelijke Nederlandse waarden en de browser rapporteerde
geen fouten of waarschuwingen. Daarmee is fase D definitief visueel geaccepteerd.

## Volgende fase

## Fase E — opportunities en testability

Status: lokaal en op staging geïmplementeerd en geaccepteerd.

- statistisch begrensde journey-frictie uit Matomo wordt een opportunity en nooit een bewezen
  probleem;
- sterke zoekprestatie plus commerciële paginarol en een materieel lage uitkomst kan als
  `underperforming_winner` worden voorgesteld;
- commerciële vraagintentie op een informatief geclassificeerde pagina kan als toetsbare
  intentmismatch worden voorgesteld;
- iedere testkandidaat krijgt één van de voorlopige meetadviezen `testable`,
  `longer_observation_needed` of `effect_measurement_preferred`;
- de pilotdrempels zijn een ruisfilter, geen universele significantiegrens en geen causaliteitsclaim;
- mobiele frictie vereist expliciet device-gesegmenteerd volume plus een materieel verschil tussen
  mobiele en desktopperformance. Het huidige datamodel levert dat volume niet betrouwbaar, zodat
  deze kandidaat terecht niet automatisch wordt aangemaakt;
- taakteksten spreken over hypothese, waarnemingen en effectmeting en tonen geen interne kansscore.

Acceptatie vereist minimaal een journey-kandidaat, een afgewezen kandidaat bij onvoldoende
context, een correct meetadvies, begrijpelijke UI-labels en bewijs dat ontbrekend mobiel volume geen
valse devicekans oplevert.

Lokale acceptatie:

- journey-frictie wordt historisch en idempotent als opportunity opgeslagen;
- underperforming-winner-, intentmismatch- en devicebewijsgrenzen zijn afzonderlijk getest;
- testadviezen en hypotheseteksten zijn in API, taak en interface regressiegedekt;
- volledige regressiesuite: 565 geslaagd, alleen de bestaande Starlette/httpx-waarschuwing;
- Ruff, JavaScript-syntax en diffcontrole: geslaagd.

Stagingacceptatie:

- API, PostgreSQL en Redis waren gezond;
- de herbruikbare fixture bevestigde de journey-opportunity, het meetadvies
  `effect_measurement_preferred`, het afwijzen van de valse devicekandidaat en herstel van de
  oorspronkelijke brondata;
- healthcheck en gereedsignaal `release-12-phase-e-ui-staging-ok`: geslaagd;
- de visuele controle bevestigde het label `Mogelijke doorstroomkans`, begrijpelijke datadekking
  (`Zoekprestatie: onbekend` en `Bezoekersgedrag: aanwezig`) en een uitklapbare onderbouwing met
  impactdomeinen, hypothesebeoordeling en het meetadvies `Effectmeting heeft voorkeur`;
- de interface toont geen interne bronnaam, ruwe score of onbewezen causaliteitsclaim.

## Volgende fase

Fase E is gereed. Productie volgt pas nadat de volledige pilot en gebruikersacceptatie zijn
afgerond.

## Fase F — informatiearchitectuur en beschrijvend leren

Status: lokaal en op staging geïmplementeerd en geaccepteerd.

- Inzichten, Kansen en Acties zijn primaire navigatiebestemmingen;
- technische signalen, URL's, wijzigingen, contentmetingen en vacatures blijven beschikbaar onder
  Metingen en worden niet als afzonderlijke productdisciplines gepresenteerd;
- Kansen opent rechtstreeks de bestaande, onderbouwde opportunityweergave;
- Acties opent de menselijke taakworkflow; bestaande issues heten in de navigatie Signalen;
- oude hashes blijven ondersteund en worden naar de nieuwe routes vertaald;
- sitegebonden effecthistorie toont pas vanaf drie vergelijkbare metingen een beschrijvend patroon;
- de leerlaag doet geen voorspelling, deelt geen klantdata tussen websites en presenteert geen
  causaliteitsclaim.

Lokale acceptatie:

- nieuwe en oude routes zijn regressiegedekt;
- JavaScript-syntax, Ruff en diffcontrole: geslaagd;
- volledige regressiesuite: geslaagd, alleen de bestaande Starlette/httpx-waarschuwing;
- stagingfixture controleert primaire navigatie, routecompatibiliteit, minimumvolume en het verbod
  op causaliteitsclaims.

Stagingacceptatie:

- API, PostgreSQL en Redis waren gezond;
- de fixture bevestigde Inzichten, Kansen en Acties, legacyroutes, minimumvolume drie en het
  ontbreken van een causaliteitsclaim;
- healthcheck en gereedsignaal `release-12-phase-f-staging-ok`: geslaagd;
- de visuele controle bevestigde de primaire navigatie en routes `#inzichten`, `#kansen` en
  `#acties`;
- Kansen opent direct de opportunityweergave, Acties de menselijke werkvoorraad en Metingen bevat
  de technische detailpagina's;
- de Effect-weergave meldde bij nul vergelijkbare metingen begrijpelijk dat nog geen historisch
  patroon beschikbaar is (`0/3`).

## Volgende fase

Het afzonderlijke productiebesluit was GO; onderstaande productieacceptatie rondt de release af.

## Productieacceptatie

- API, PostgreSQL, Redis en renderworker waren gezond;
- migratie `0060` stond op head, rendering was actief en de accessibility-engine was beschikbaar;
- de statische fase-F-controle, healthcheck en deployment-drain slaagden; één gepauzeerde crawl is
  hervat;
- gereedsignaal `release-12-production-ok`: geslaagd;
- de visuele controle bevestigde de primaire navigatie Inzichten, Kansen en Acties;
- `#inzichten` opende de inzichtweergave, `#kansen` de onderbouwde opportunityweergave en `#acties`
  de menselijke werkvoorraad;
- de Effect-weergave toonde bij onvoldoende vergelijkbare productiehistorie correct de ondergrens
  `0/3` en deed geen causaliteitsclaim.

Release 12 is daarmee volledig geaccepteerd in productie.

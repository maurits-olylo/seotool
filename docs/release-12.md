# Release 12 — Continuous Website Improvement-pilot

Status: fase B lokaal en op staging geaccepteerd; nog niet naar productie gedeployed.

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

Status: lokaal geïmplementeerd en integraal getest; nog niet op staging geaccepteerd.

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

## Volgende fase

Na lokale eindcontrole en stagingacceptatie kan fase D starten met uitlegbare cross-domain
prioritering. Fase D start pas na afzonderlijke bevestiging.

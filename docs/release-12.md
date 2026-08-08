# Release 12 — Continuous Website Improvement-pilot

Status: fase B lokaal geïmplementeerd en getest; nog niet gedeployed.

## Doel en afbakening

Release 12 gebruikt accessibility als eerste extra kwaliteitsbron binnen dezelfde verbetercyclus
als SEO-signalen. De release bouwt geen WCAG-score, certificering, apart dashboard of generieke
rules engine. Het ontwerp staat in `docs/continuous-website-improvement-design.md`.

## Fase A — architectuur

Status: afgerond.

De bestaande keten `signaal → issue → taak → verificatie → interventie → effect` blijft
leidend. Accessibility is een bron en bewijsdomein binnen die keten.

## Fase B — accessibility-fundament

Status: lokaal geïmplementeerd en getest.

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
- de stagingimagebuild en een synthetische browserproef zijn daarom verplichte acceptatiepunten
  voordat fase B als deploymentgereed geldt.

## Volgende fase

Fase C voegt componenthandtekeningen, bereik, multi-issue taakcreatie, gerichte verificatie en
regressie toe. Zij start pas na afzonderlijke bevestiging.

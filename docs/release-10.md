# Release 10 — Meetbare SEO-effectontwikkeling

Status: geaccepteerd en op 7 augustus 2026 naar staging en productie uitgerold.

## Doel en afbakening

Release 10 koppelt uitgevoerde aanbevelingstaken aan controleerbare KPI-ontwikkeling. De release
toont waargenomen samenhang en claimt geen causale attributie, algemene effectscore of gegarandeerde
groei. Bestaande taak-, URL-, classificatie- en metriekhistorie blijft de bron.

## Meetbare interventies

- Migration `0056` voegt immutable `effect_interventions` toe zonder bestaande data te kopiëren of
  te herschrijven.
- Een taak met een volledige controlescope start bij status `implemented` automatisch een gerichte
  verificatie.
- Een bevestigde oplossing sluit de taak, resolveert het primaire issue en legt de interventie
  automatisch en idempotent vast.
- Een niet opgeloste taak keert terug naar `in_progress`; alleen een onzekere uitkomst vraagt
  menselijke beoordeling.
- De registratie bevriest taakdefinitie, implementatiemoment, URL-rollen en de toen geldige
  effectieve contentclassificatie.
- De actie is tenantgebonden en idempotent. Herhaald vastleggen maakt geen duplicaat en wijzigt het
  eerdere bewijs niet.

## Versieerbare cohortberekening

- Migration `0057` voegt immutable `effect_evaluations` toe met inputhash en methodeversie.
- Methode 1 vergelijkt een basis- en observatieperiode van elk 28 dagen en vereist 42 dagen
  maturiteit na de laatste interventie.
- Minimaal 14 meetdagen GSC-dekking zijn in beide perioden nodig voor `development_visible`.
- GSC wordt gecombineerd met precies één ingestelde primaire analyticsbron: GA4 of Matomo.
- Overlappende URL's worden binnen één cohort gededupliceerd en als confidencefactor geteld.
- Toegestane uitkomsten blijven conservatief: te vroeg, onvoldoende data, niet vergelijkbaar of
  ontwikkeling zichtbaar.

## API en interface

- De normale taakworkflow bevat geen aparte verificatie- of meetbaarheidsactie.
- De bestaande Content-sectie bevat een afzonderlijke Effect-tab en gebruikt de bestaande
  periodekeuze als interventiecohort.
- De scheduler hercontroleert te vroege of onvoldoende onderbouwde evaluaties automatisch.
- De Effect-tab is read-only; gewoon laden schrijft niets en start geen achtergrondtaak.
- Het overzicht toont cohort, basis- en observatieperiode, KPI-verschillen, brondekking, URL-aantal,
  overlap, methodeversie en een expliciete niet-causale bewijsnotitie.
- Eerdere evaluaties blijven zichtbaar en worden nooit bij hercontrole overschreven.

## Lokale acceptatie

- Ruff slaagt voor de volledige repository en de JavaScript-syntaxcontrole is groen.
- De volledige testsuite slaagt met 484 tests en alleen de bestaande Starlette/httpx-waarschuwing.
- Alembic heeft één lineaire head op `0057`; de overgang `0056` naar `0057` is geïsoleerd getest.
- Basis- en staging-Composeconfiguratie zijn geldig met `.env.example`.
- API-tests bevestigen expliciete, idempotente interventieregistratie, afwijzing zonder URL-scope,
  historische evaluatielisting en periodevalidatie.
- Een taaktype zonder automatische verificatieregel blijft leesbaar en toont een niet-ondersteunde
  verificatiestatus in plaats van een serverfout.
- UI-tests bevestigen de automatische taakroute, read-only Effect-tab en cacheversie.
- Beide migrations zijn additief en herschrijven geen data. Een extra releaseback-up is daarom niet
  vereist; een gezonde bestaande herstelroute blijft wel een deploymentvoorwaarde.

## Stagingacceptatie

Staging heeft aangetoond:

- API, PostgreSQL en Redis zijn gezond op migration-head `0057`;
- PageSpeed en JavaScript-rendering blijven uitgeschakeld;
- een synthetische taak met volledige URL-scope start bij `implemented` automatisch één controle;
- `resolved` sluit de taak, resolveert het issue en maakt exact één interventie;
- `not_resolved` zet de taak terug naar `in_progress`;
- Effect toont correcte lege, te-vroege en onvoldoende-data toestanden;
- laden van Content of Effect start geen crawl, import, taak of berekening;
- desktop en 390 px hebben geen documentoverflow of browserfouten.

De stagingstack bevat conform het isolatieontwerp geen actieve crawlworkers of scheduler. De
uitkomstovergangen en periodieke effecthercontrole zijn daarom lokaal door regressietests gedekt;
de read-only interface en operationele randvoorwaarden zijn op staging geaccepteerd.

## Productieacceptatie

- API, PostgreSQL, Redis, scheduler en alle geraakte crawlworkers zijn gezond op migration-head
  `0057`.
- De schedulerrol heeft uitsluitend het benodigde aanvullende INSERT-recht op
  `effect_evaluations` gekregen.
- De verplichte crawl-drain was vóór de update `safe=true`; na acceptatie zijn vier gepauzeerde
  crawls hervat en is de drain beëindigd.
- De Effect-tab toont de automatische werkwijze zonder handmatige registratie- of berekenknop.
- Desktop en 390 px hebben geen documentoverflow of browserfouten.

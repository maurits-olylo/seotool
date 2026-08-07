# Release 10 — Meetbare SEO-effectontwikkeling

Status: lokaal geaccepteerd; staging en productie nog niet uitgevoerd.

## Doel en afbakening

Release 10 koppelt uitgevoerde aanbevelingstaken aan controleerbare KPI-ontwikkeling. De release
toont waargenomen samenhang en claimt geen causale attributie, algemene effectscore of gegarandeerde
groei. Bestaande taak-, URL-, classificatie- en metriekhistorie blijft de bron.

## Meetbare interventies

- Migration `0056` voegt immutable `effect_interventions` toe zonder bestaande data te kopiëren of
  te herschrijven.
- Alleen een taak met status `implemented` of `closed`, een implementatiemoment en minimaal één URL
  kan expliciet als interventie worden vastgelegd.
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

- Een uitgevoerde taak bevat de expliciete actie `Maak meetbaar`.
- De bestaande Content-sectie bevat een afzonderlijke Effect-tab en gebruikt de bestaande
  periodekeuze als interventiecohort.
- `Bereken effect` is een expliciete mutatie; gewoon laden schrijft niets en start geen achtergrondtaak.
- Het overzicht toont cohort, basis- en observatieperiode, KPI-verschillen, brondekking, URL-aantal,
  overlap, methodeversie en een expliciete niet-causale bewijsnotitie.
- Eerdere evaluaties blijven zichtbaar en worden nooit bij hercontrole overschreven.

## Lokale acceptatie

- Ruff slaagt voor de volledige repository en de JavaScript-syntaxcontrole is groen.
- De volledige testsuite slaagt met 483 tests en alleen de bestaande Starlette/httpx-waarschuwing.
- Alembic heeft één lineaire head op `0057`; de overgang `0056` naar `0057` is geïsoleerd getest.
- Basis- en staging-Composeconfiguratie zijn geldig met `.env.example`.
- API-tests bevestigen expliciete, idempotente interventieregistratie, afwijzing zonder URL-scope,
  historische evaluatielisting en periodevalidatie.
- Een taaktype zonder automatische verificatieregel blijft leesbaar en toont een niet-ondersteunde
  verificatiestatus in plaats van een serverfout.
- UI-tests bevestigen de taakactie, Effect-tab, expliciete berekenroute en cacheversie.
- Beide migrations zijn additief en herschrijven geen data. Een extra releaseback-up is daarom niet
  vereist; een gezonde bestaande herstelroute blijft wel een deploymentvoorwaarde.

## Stagingacceptatie

Staging moet vóór productie aantonen:

- API, PostgreSQL en Redis zijn gezond op migration-head `0057`;
- PageSpeed en JavaScript-rendering blijven uitgeschakeld;
- taakdetail toont `Maak meetbaar` alleen voor uitgevoerde of afgesloten taken;
- een synthetische uitgevoerde taak met URL-scope wordt exact één interventie;
- dezelfde actie opnieuw uitvoeren meldt hergebruik en maakt geen duplicaat;
- Effect toont correcte lege, te-vroege en onvoldoende-data toestanden;
- laden van Content of Effect start geen crawl, import, taak of berekening;
- desktop en 390 px hebben geen documentoverflow of browserfouten.

Productiedeployment blijft geblokkeerd totdat deze stagingacceptatie expliciet is afgerond.

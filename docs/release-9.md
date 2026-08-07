# Release 9 — Opportunity-engine en contextuele data-assistent

Status: fase 1 lokaal geïmplementeerd en nog niet gedeployed.

## Doel en afbakening

Release 9 prioriteert aantoonbare kansen op basis van potentieel, beïnvloedbare frictie,
bewijskracht en uitvoerbaarheid/bereik. De score is geen algemene SEO-score en voorspelt geen
percentage extra verkeer. De eerste versie werkt zonder AI-provider en gebruikt uitsluitend
tenantgebonden gegevens die al in SEO Monitor aanwezig zijn.

## Fase 1 — Versieerbaar score- en bewijsfundament

- Migration `0055` voegt historische opportunity-evaluaties toe voor pagina's, URL-families en
  gedeelde oorzaken, zonder bestaande data te classificeren of te herschrijven.
- Iedere evaluatie bewaart analyseperiode, inputhash, formuleversie, vier afzonderlijke deelscores,
  totaalscore, prioriteitsklasse, brondekking, bijdragers en compact bewijs.
- De vaste formuleversie `opportunity-score-2026-08-07-v1` weegt potentieel 40%, beïnvloedbare
  frictie 25%, bewijskracht 20% en uitvoerbaarheid/bereik 15%.
- Ontbrekende dimensies blijven onbekend en leveren geen totaalscore. Bewijskracht onder 40 begrenst
  de uitkomst tot `insufficient_evidence`; middelmatige bewijskracht kan nooit een hoge kans maken.
- Dezelfde scope, inputhash en formuleversie maken geen dubbele historische evaluatie.
- De beveiligde lees-API retourneert uitsluitend evaluaties van een website binnen de
  geautoriseerde tenant. Automatische patroonberekening volgt in fase 2.

Acceptatie:

- alle deel- en totaalscores liggen tussen 0 en 100 en zijn herleidbaar tot centrale gewichten;
- ontbrekende data wordt niet als nul behandeld;
- lage bewijskracht kan geen hoge prioriteit opleveren;
- identieke input en formuleversie zijn idempotent;
- tenantoverschrijdend lezen wordt geweigerd;
- Alembic heeft één lineaire head op `0055`, Ruff en de gerichte tests slagen.

Lokale acceptatie:

- Alembic heeft één lineaire head op `0055`, direct vanaf `0054`.
- Ruff slaagt voor de volledige repository; alle nieuwe en gewijzigde Pythonbestanden voldoen aan
  de formattercontrole.
- De twee nieuwe score-, idempotentie-, historie-, API- en tenanttests en alle bestaande
  opportunity- en API-regressies slagen.
- De volledige testsuite slaagt met 468 tests en alleen de bestaande Starlette/httpx-waarschuwing.
- Migration `0055` is additief, voert geen backfill of dataherschrijving uit en vereist daarom geen
  extra releaseback-up.

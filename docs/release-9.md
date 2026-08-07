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

## Fase 2 — Eerste deterministische opportunitypatronen

Status: lokaal geïmplementeerd en nog niet gedeployed.

- Een expliciete evaluatieactie combineert bestaande GSC-paginametrics met actieve, passende
  crawlerissues en schrijft uitsluitend nieuwe historische evaluaties weg.
- Een CTR-kans vereist minimaal 250 vertoningen, gemiddelde positie 4–15, CTR onder 2,5% en een
  actieve title- of meta-descriptionfrictie.
- Een pagina-twee-kans vereist minimaal 150 vertoningen, positie 11–20, een actuele zekere
  niet-gemengde intentieclassificatie en actieve thin- of near-duplicate-contentfrictie.
- Een interne-linkkans vereist minimaal 150 vertoningen, crawldiepte vier of hoger en een actief
  diepte- of interne-ondersteuningsissue.
- Iedere evaluatie bewaart positieve, negatieve en contextuele bijdragers plus GSC- en issuebewijs.
  De patroonversie is expliciet en dezelfde periode/input blijft idempotent.
- Alleen actieve, indexeerbare URL's met status 200 komen in aanmerking. Functionele zoekpagina's,
  discovery-only varianten en issues met opgelost, geverifieerd, genegeerd of geaccepteerd risico
  leveren geen kans op.
- De meetperiode omvat minimaal 28 dagen. Ontbrekende analyticsdekking blijft zichtbaar en wordt
  niet als nul geïnterpreteerd.

Acceptatie:

- ieder patroon vereist zowel meetbaar potentieel als een aannemelijk beïnvloedbare frictie;
- drempels, formule- en patroonversie en alle bijdragers zijn uitlegbaar;
- dezelfde input maakt geen dubbele evaluatie;
- functionele pagina's en geaccepteerde risico's leveren geen schijnkans;
- gerichte patroon- en regressietests, Ruff en de volledige testsuite slagen.

Lokale acceptatie:

- Twee gerichte tests bevestigen alle drie patronen, bewijsopbouw, idempotentie, functionele-
  paginafilters, geaccepteerd risico en de minimale periode.
- De API-regressie bevestigt dat evaluaties niet buiten de geautoriseerde tenant kunnen worden
  gestart.
- Ruff en de formattercontrole voor de fasebestanden slagen; Alembic blijft op de lineaire head
  `0055` en deze fase vereist geen nieuwe migration.
- De volledige testsuite slaagt met 470 tests en alleen de bestaande Starlette/httpx-waarschuwing.

## Fase 3 — Transparante API en interface

Status: lokaal geïmplementeerd en nog niet gedeployed.

- Het bestaande Contentscherm toont historische kansbeoordelingen zonder nieuwe hoofdnavigatie.
- Iedere beoordeling toont de vier deelscores, totaalscore, prioriteitsklasse, bijdragers,
  brondekking, formuleversie en het verschil met de vorige meting van dezelfde scope.
- Ontbrekende bronnen blijven expliciet `onbekend`; een ontbrekende score wordt niet als nul
  gepresenteerd. De onderliggende bijdragers zijn op aanvraag zichtbaar.
- Berekenen gebeurt uitsluitend via de expliciete knop `Bereken kansen`; laden van het scherm
  wijzigt geen data en activeert geen contentwijziging.
- Een bruikbare kans kan handmatig naar de bestaande taakworkflow worden gepromoveerd. Een actieve
  taak voor hetzelfde patroon en dezelfde scope wordt hergebruikt, zodat herhaald klikken geen
  duplicaat maakt. Beoordelingen met onvoldoende bewijs kunnen geen taak worden.
- De taak bewaart de evaluatie-, scope-, patroon- en formuleversie als verificatiecontext en koppelt
  de primaire URL en geldige onderliggende issues.

Acceptatie:

- alle scores en ontbrekende dekking zijn zichtbaar en herleidbaar;
- een vorige meting wordt alleen binnen dezelfde scope en formuleversie vergeleken;
- berekenen en taakpromotie zijn expliciete gebruikersacties;
- taakpromotie is tenantgebonden en dedupliceert actieve taken;
- de bestaande contentcontrolepunten blijven beschikbaar naast de gescoorde kansen;
- API-, UI-, lint- en regressietests slagen zonder nieuwe migration.

Lokale acceptatie:

- De API- en UI-regressies bevestigen URL-weergave, historische vergelijking, expliciete acties,
  tenantisolatie en hergebruik van een bestaande actieve taak.
- De fasebestanden voldoen aan Ruff en de JavaScript-syntaxcontrole; Alembic blijft op de lineaire
  head `0055` en deze fase vereist geen migration.
- De volledige testsuite slaagt met 472 tests en alleen de bestaande Starlette/httpx-waarschuwing.

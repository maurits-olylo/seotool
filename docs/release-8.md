# Release 8 — Zoekintentie en contentanalyse

Status: in uitvoering; fase 1 is lokaal geïmplementeerd en nog niet gedeployed.

## Doel en afbakening

Release 8 maakt per succesvolle, indexeerbare canonical HTML-URL uitlegbaar zichtbaar welke
zoekintentie, klantreisfase en strategische contentrol waarschijnlijk van toepassing zijn. De
conclusie combineert bestaande crawlerinhoud, GSC-querydata en de gekozen primaire analyticsbron.
Het systeem bewaart bewijs, dekking, confidence en versies en presenteert onvoldoende bewijs nooit
als hard probleem.

De release introduceert geen algemene SEO-score, verplichte lineaire funnel, automatische
contentwijzigingen of AI-provider. GA4 en Matomo blijven afzonderlijke bronnen en worden nooit
stilzwijgend opgeteld. JavaScript-rendering en PageSpeed blijven uitgeschakeld.

## Bestaande basis

- `urls` en `url_snapshots` leveren blijvende URL-identiteit, canonical, indexeerbaarheid,
  hoofdcontent, metadata en hashes.
- `search_console_query_metrics` bewaart dagelijkse query-/paginametrics met gekoppelde URL-ID's.
- De provider-onafhankelijke analyticslaag en expliciete primaire analyticsbron zijn sinds Release
  7 actief.
- `content_intent_insights.py` bevat al een beperkte heuristische GSC-kansdetectie. Deze blijft
  bruikbaar, maar is geen duurzaam classificatie- of bewijsmodel.
- Tenantautorisatie, auditlogging, retentie en privacyverwijdering zijn platformvoorwaarden voor
  alle nieuwe routes en tabellen.

## Fase 1 — Versieerbaar classificatie- en bewijsfundament

Status: lokaal geïmplementeerd. Migration `0052` en een deterministische domeinlaag zijn toegevoegd
zonder bestaande data automatisch te classificeren.

- Leg vaste waarden vast voor zoekintentie, klantreisfase en contentrol, inclusief `uncertain`.
- Bewaar classificaties historisch per website en URL met analyseperiode, inputhash,
  classificatieversie, confidence, brondekking, waarschijnlijkheidsverdeling en compact bewijs.
- Bewaar automatische uitkomsten en handmatige overrides afzonderlijk. Een gelockte override
  blijft behouden totdat een bevoegde gebruiker die expliciet reset.
- Voeg websitegebonden branded termen en optionele sectorsjablooninstellingen toe zonder
  klantoverschrijdende defaults of persoonsgegevens.
- Dwing tenantautorisatie af op alle toekomstige lees- en schrijfroutes en log overridewijzigingen
  in de bestaande security-auditlaag.
- Voeg model-, migration-, constraint- en domeinlogictests toe. De migration is additief en voert
  geen backfill of dataherschrijving uit.

Acceptatie:

- waarschijnlijkheden zijn geldig, niet-negatief en tellen binnen afrondingsmarge op tot één;
- dezelfde inputhash en classificatieversie maken geen dubbele automatische classificatie;
- een gelockte handmatige override overleeft automatische heranalyse;
- classificaties kunnen niet buiten de geautoriseerde tenant worden gelezen of gewijzigd;
- Alembic heeft één lineaire head op `0052`, Ruff en de relevante tests slagen.

Lokale acceptatie:

- Alembic heeft één lineaire head op `0052`, direct vanaf `0051`.
- De drie gerichte domein-, API-, tenant- en auditlogtests slagen.
- Ruff slaagt voor de volledige applicatiemap, de migration en de nieuwe tests.
- De migration is uitsluitend additief en voert geen backfill of dataherschrijving uit; een extra
  releaseback-up is daarom niet nodig.

## Fase 2 — Deterministische pagina- en queryclassificatie

Status: lokaal geïmplementeerd en nog niet gedeployed.

- Classificeer crawlerinhoud en GSC-query's uitlegbaar op basis van versieerbare regels.
- Cache queryclassificatie per genormaliseerde query, taal en markt.
- Bereken pagina-uitkomsten gewogen op vertoningen en klikken met expliciete dekking.
- Sla alleen een nieuwe historische uitkomst op bij gewijzigde inputhash of classificatieversie.
- Maak geen harde actie bij ontbrekende of tegenstrijdige brondekking.

Implementatie en lokale acceptatie:

- Migration `0053` voegt een gedeelde, contextgebonden querycache toe met unieke combinatie van
  genormaliseerde query, taal, land en classificatieversie.
- Regelversie `intent-rules-2026-08-07-v1` classificeert Nederlandse en Engelse query- en
  paginasignalen zonder externe provider. Branded termen blijven websitegebonden en beïnvloeden
  alleen de uitkomst voor de betreffende website.
- Alleen actieve, succesvolle, indexeerbare HTML-pagina's met eigen geldige canonical en een
  bruikbare contenthash worden geclassificeerd.
- GSC-vertoningen en klikken wegen mee in de paginaverdeling; crawler- en GSC-dekking blijven
  afzonderlijk zichtbaar in het bewijs.
- Dezelfde inputhash, analyseperiode en regelversie maken geen tweede paginaclassificatie.
- Drie gerichte regel-, bewijs-, cache- en idempotentietests slagen; Ruff is schoon en Alembic heeft
  één lineaire head op `0053`.

## Fase 3 — Verdelingen, mismatch en contentkansen

Status: lokaal geïmplementeerd en nog niet gedeployed.

- Voeg website-, cluster- en paginaverdelingen toe.
- Detecteer intentiemismatch, aantoonbare queryoverlap, ontbrekende vervolgstappen en contenthiaten.
- Behandel uitkomsten als controle of kans met onderliggend bewijs, niet als automatisch defect.
- Hergebruik de bestaande taak- en issuelifecycle zonder dubbele aanbevelingen te maken.

Implementatie en lokale acceptatie:

- De beveiligde website-API levert website-, eerste-padcluster- en paginaverdelingen met periode,
  classificatiedekking, GSC-dekking, confidence en effectieve handmatige overrides.
- Een intentiemismatch vereist een gelockte handmatige keuze, een afwijkende automatische uitkomst
  en minimaal `0.65` confidence.
- Queryoverlap vereist minimaal twee pagina's met ieder 50 vertoningen, samen 150 vertoningen, een
  aandeel van minimaal 20% voor de tweede pagina en dezelfde niet-onzekere intentie.
- Een contenthiaat vereist minimaal 75 vertoningen en een query-intentie die met voldoende bewijs
  afwijkt van alle gekoppelde pagina-intenties. De tekst adviseert eerst bestaande pagina's te
  controleren en stelt nooit automatisch nieuwe content verplicht.
- Kansen zijn standaard read-only. Alleen een expliciete gebruikersactie maakt een bestaande
  aanbevelingstaak met URL-scope, activiteitenregistratie en stabiele opportunitysleutel aan;
  herhaling retourneert dezelfde actieve taak.
- Twee gerichte regressietests bevestigen verdelingen, drempels, mismatch, contenthiaat,
  queryoverlap en taakdeduplicatie. Ruff is schoon; deze fase vereist geen migration.

## Fase 4 — Klantreis en primaire analyticsbron

- Voeg landingsgedrag, beschikbare vervolgstappen, microconversies en primaire conversies toe.
- Presenteer routes als geobserveerde samenhang en claim geen causale attributie.
- Toon ontbrekende transition- of eventdekking als onbekend.
- Respecteer uitsluitend de expliciet gekozen primaire analyticsbron.

## Fase 5 — Interface en performance

- Voeg compacte schermen toe voor Overzicht, Pagina's, Clusters, Doorstroom, Kansen en Instellingen.
- Toon bronnen, periode, dekking, confidence en zwaarst wegend bewijs bij iedere conclusie.
- Bundel de uitgestelde Matomo-koppelingsuitleg en de roadmapafspraken voor parallel laden,
  skeletons, paginering en meetbare endpointdoorlooptijden.
- Behoud bruikbaarheid zonder horizontale overflow op 390 px.

## Fase 6 — Integrale acceptatie en deployment

- Voer volledige lokale lint-, test-, migration- en Compose-controles uit.
- Valideer met uitsluitend synthetische data op staging, inclusief tenantisolatie en overrides.
- Deploy daarna via een exact getest Git-archive en de vaste interactieve NAS-route.
- Start geen crawl of historische import uitsluitend voor releasecontrole.
- Leg productiehealth, migratiehead, bronafbakening en uitgeschakelde rendering/PageSpeed vast.

## Uitgesteld

Effectmeting na uitgevoerde aanbevelingen, externe SERP-data en AI-ondersteunde twijfelgevallen
blijven latere modules. Release 7a-B fase 6B blijft afzonderlijk geparkeerd als harde gate vóór de
Friends & Family-release en blokkeert de ontwikkeling van Release 8 niet.

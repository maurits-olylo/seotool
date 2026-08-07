# Release 8 — Zoekintentie en contentanalyse

Status: afgerond en op 7 augustus 2026 lokaal, op staging en op productie geaccepteerd vanaf
releasecommit `1b6b1ef`.

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

Status: lokaal geïmplementeerd en nog niet gedeployed.

- Voeg landingsgedrag, beschikbare vervolgstappen, microconversies en primaire conversies toe.
- Presenteer routes als geobserveerde samenhang en claim geen causale attributie.
- Toon ontbrekende transition- of eventdekking als onbekend.
- Respecteer uitsluitend de expliciet gekozen primaire analyticsbron.

Implementatie en lokale acceptatie:

- De beveiligde journey-API gebruikt uitsluitend de gekozen primaire analyticsbron en telt GA4 en
  Matomo nooit bij elkaar op. Gelockte classificatie-overrides bepalen de effectieve klantreisfase
  en contentrol.
- Matomo importeert naast paginaweergaven en conversies ook instapsessies, bounces en exits.
  Migration `0054` voegt deze drie additieve velden zonder dataherschrijving toe.
- Een mogelijk onbedoeld landing-eindpunt vereist minimaal 25 instapsessies, vijf vergelijkbare
  pagina's met samen minimaal 200 instapsessies, minstens tien procentpunt praktisch verschil en
  een eenzijdige exacte binomiale toets met minimaal 90% betrouwbaarheid.
- Een Benjamini-Hochberg-correctie begrenst de false-discovery-rate op 10% wanneer meerdere
  pagina's tegelijk worden getest. Pagina's met conversies, onvoldoende classificatie of een
  logische navigatierol leveren geen signaal op.
- De aanbeveling vraagt eerst te controleren of de pagina bewust een eindpunt is en stelt pas
  daarna interne links of een CTA voor. Het signaal wordt niet als causaal defect gepresenteerd.
- Echte pagina-naar-paginatransities worden niet uit bouncegegevens afgeleid. Matomo-transities
  blijven expliciet `not_imported`; GA4-transities blijven `unknown`. BigQuery is voor het huidige
  productdoel bewust niet toegevoegd.
- Negentien cumulatieve Release 8-tests slagen, inclusief bronselectie, classificatie-overrides,
  statistische drempels, Matomo-import en ruisfilters. Ruff is schoon en Alembic heeft één lineaire
  head op `0054`.

## Fase 5 — Interface en performance

Status: lokaal geïmplementeerd en nog niet gedeployed.

- Voeg compacte schermen toe voor Overzicht, Pagina's, Clusters, Doorstroom, Kansen en Instellingen.
- Toon bronnen, periode, dekking, confidence en zwaarst wegend bewijs bij iedere conclusie.
- Bundel de uitgestelde Matomo-koppelingsuitleg en de roadmapafspraken voor parallel laden,
  skeletons, paginering en meetbare endpointdoorlooptijden.
- Behoud bruikbaarheid zonder horizontale overflow op 390 px.

Implementatie en lokale acceptatie:

- De bestaande Analyse-navigatie bevat één compact Contentscherm met interne tabbladen voor
  Overzicht, Pagina's, Clusters, Doorstroom, Kansen en Instellingen. Hierdoor blijft de
  hoofdnavigatie beperkt en consistent met de bestaande informatiearchitectuur.
- Kansen, journeydata en instellingen laden parallel. De interface toont de afzonderlijk gemeten
  endpointdoorlooptijd, analyseperiode, primaire analyticsbron, brondekking en ontbrekende data.
- De paginalijst rendert maximaal 25 regels per pagina. Distributies, clusters en kansen gebruiken
  compacte kaarten en bewijslabels; een kans kan expliciet naar de bestaande taakworkflow worden
  gepromoveerd.
- Websitegebonden branded termen en het optionele sectorsjabloon zijn vanuit Instellingen
  bewerkbaar. Opslaan start bewust geen automatische classificatie of crawl.
- Pagina-naar-paginatransities en microconversies worden niet gesuggereerd wanneer de bron ze niet
  levert. Het Doorstroomscherm vermeldt die dekking expliciet naast de statistisch onderbouwde
  landing-eindpunten.
- De visuele controle slaagt op desktop en 390 px. Op 390 px is de documentbreedte exact gelijk aan
  de viewport; alleen de tabstrip scrollt horizontaal binnen zijn eigen begrenzing.
- JavaScript-syntaxcontrole, Ruff, 72 gerichte API-, interface-, classificatie-, kans-, journey- en
  Matomo-tests slagen. Alembic houdt één lineaire head op `0054`; deze fase heeft geen migration.

## Fase 6 — Integrale acceptatie en deployment

Status: afgerond op lokaal, staging en productie.

- Voer volledige lokale lint-, test-, migration- en Compose-controles uit.
- Valideer met uitsluitend synthetische data op staging, inclusief tenantisolatie en overrides.
- Deploy daarna via een exact getest Git-archive en de vaste interactieve NAS-route.
- Start geen crawl of historische import uitsluitend voor releasecontrole.
- Leg productiehealth, migratiehead, bronafbakening en uitgeschakelde rendering/PageSpeed vast.

Lokale acceptatie:

- Ruff-linting slaagt voor de volledige repository. De Release 8-bestanden voldoen ook aan de
  formattercontrole; een repositorybrede formattercontrole meldt 62 al bestaande bestanden door
  de nieuwere Ruff-versie in de verse lokale testomgeving en is daarom niet automatisch toegepast.
- De volledige testsuite slaagt met 466 tests en alleen de bestaande Starlette/httpx-waarschuwing.
- De JavaScript-syntaxcontrole van de interface slaagt.
- Alembic heeft één lineaire head op `0054`, na de additieve migrations `0052`, `0053` en `0054`.
- De basis-, productie- en staging-Composeconfiguraties zijn geldig met hun voorbeeldconfiguratie.
- De lokale Docker-daemon was niet actief. De imagebuild en container-healthchecks worden daarom
  op staging uitgevoerd vanaf de exacte acceptatiecommit en niet als lokaal bewijs gepresenteerd.
- De migrations zijn additief en herschrijven geen bestaande data. Een extra releaseback-up is
  niet nodig; de bestaande geverifieerde herstelroute blijft een deploymentvoorwaarde.
- Er is voor deze acceptatie geen crawl of historische import gestart. De bronafbakening blijft één
  expliciet gekozen primaire analyticsbron; GA4 en Matomo worden niet gecombineerd en
  `PAGESPEED_ENABLED=false` en `RENDERING_ENABLED=false` blijven deploymentvoorwaarden.

Stagingacceptatie:

- Releasecommit `1b6b1ef` is via het vaste Git-archive en de interactieve NAS-route gedeployed.
- API, PostgreSQL en Redis zijn gezond op migration-head `0054`; de nieuwe routes zijn aanwezig en
  PageSpeed en JavaScript-rendering blijven uitgeschakeld.
- De synthetische stagingwebsite bevat bewust geen classificeerbare crawldata. De interface toont
  daardoor correcte lege toestanden zonder een crawl of historische import te starten;
  tenantisolatie, gelockte overrides, classificatie-idempotentie en kanspromotie blijven gedekt
  door de geslaagde regressietests.
- Classificaties, kansen, doorstroom en instellingen laden parallel. De gemeten endpointtijden lagen
  tussen 64 en 129 ms en ontbrekende brondekking werd expliciet weergegeven.
- Op 390 px waren document- en viewportbreedte exact gelijk. Er trad geen documentoverflow op en
  de browser rapporteerde geen fouten of waarschuwingen.

Productieacceptatie:

- Dezelfde releasecommit `1b6b1ef` is na een veilige crawl-drain gedeployed. De additieve migrations
  zijn zonder extra releaseback-up toegepast en Alembic rapporteert head `0054`.
- API, integration-worker, PostgreSQL en Redis zijn gezond. De contentanalyseroutes zijn aanwezig;
  PageSpeed en JavaScript-rendering blijven uitgeschakeld voor API en integration-worker.
- De Contentinterface opent voor bestaande productieklanten zonder analyse, crawl of import te
  starten. De drie gemeten endpoints reageerden binnen 51 tot 141 ms en nog ontbrekende
  classificaties werden als lege toestand gepresenteerd.
- Op 390 px waren document- en viewportbreedte exact gelijk en trad geen documentoverflow op. De
  browser rapporteerde geen fouten of waarschuwingen.
- De crawl-drain meldde vóór vrijgave `active=true safe=true` met nul gevolgde of wachtende taken en
  eindigde na alle controles op `active=false` zonder taken te hervatten.

## Uitgesteld

Effectmeting na uitgevoerde aanbevelingen, externe SERP-data en AI-ondersteunde twijfelgevallen
blijven latere modules. Release 7a-B fase 6B blijft afzonderlijk geparkeerd als harde gate vóór de
Friends & Family-release en blokkeert de ontwikkeling van Release 8 niet.

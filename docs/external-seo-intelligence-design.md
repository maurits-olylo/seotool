# Externe SEO-intelligence — analyse en ontwerp

Status: ontwerpbesluit; kosteloze contractvoorbereiding gestart
Datum: 2026-08-08  
Scope: externe SERP-, autoriteits-, concurrentie- en keywordcontext

Implementatiestatus:

- vraagdekking is provider-onafhankelijk beschikbaar als `answered`, `partial`, `implicit` of
  `missing`;
- genormaliseerde SERP- en AI-citationcontracten, capability-protocols en Nederlandse fixtures
  zijn lokaal beschikbaar;
- requests, genormaliseerde observations en usage kunnen tenantgebonden worden opgeslagen; cache,
  dagelijkse idempotency, maandbudget en actieve-scopelimiet worden vóór toelating afgedwongen;
- een read-only first-party selector kiest begrensd belangrijke vraag-paginacombinaties op basis
  van GSC-vraag, indexeerbaarheid, paginabelang, contentrol en URL-familie; webshops hoeven daardoor
  geen volledige URL × vraag-matrix op te bouwen;
- één observation wordt conservatief geïnterpreteerd en creëert geen autonome kwaliteitsclaim;
- de feature staat standaard uit; een echte provideradapter, credentials, scheduler en betaalde
  calls zijn nog bewust niet gebouwd.

## 1. Executive summary

SEO Monitor moet externe data alleen ophalen wanneer een bestaand signaal daardoor tot een betere
beslissing leidt. De eerste Pareto-toepassing is daarom **gerichte SERP-context voor belangrijke
queries die al uit GSC komen**, niet een algemene ranktracker, backlinkdatabase of keywordtool.

De codebase heeft de benodigde basis al: first-party zoek- en gedragsdata, URL- en
wijzigingshistorie, contentclassificaties, inzichten, opportunity scoring, taken, verificatie en
effectmetingen. Ook bestaan versieerbare output, `input_hash`, `source_coverage`, confidence,
evidence, queues, retries, tenantautorisatie en retentiebeleid. Externe intelligence hoort deze
engines te verrijken en mag geen tweede adviesengine worden.

DataForSEO is een kandidaat-provider, geen architectuurkeuze. Voor selectie zijn eerst een kleine
Nederlandse kwaliteitstest en een actuele kostenvergelijking nodig. Tot F&F blijven automatische
betaalde calls uit. Voor F&F worden alleen het contract, fixtures, kostengrenzen en een handmatige
validatieroute voorbereid.

## 2. Huidige situatie in de codebase

De actuele datastroom is in hoofdlijnen:

1. crawler, GSC, Bing, GA4 of Matomo leveren eigen waarnemingen;
2. URL-register, snapshots en changes bewaren identiteit en historie;
3. issues, Content en Insights interpreteren de waarnemingen;
4. opportunity scoring voegt potentieel, frictie, bewijs en uitvoerbaarheid samen;
5. aanbeveling en taak sturen uitvoering en automatische verificatie;
6. Effect bewaart interventies en beoordeelt latere KPI-ontwikkeling zonder causaliteit te claimen.

De relevante implementaties zijn onder meer:

- `app/models/integrations.py`: GSC-, Bing-, GA4-, Matomo- en Bing-linkdata;
- `app/services/consultant_insights.py`: samengestelde inzichten uit zoek- en gedragsdata;
- `app/services/content_analysis.py`: versieerbare intentie- en contentclassificatie;
- `app/models/opportunities.py` en `app/services/opportunity_scoring.py`: evidence-based prioriteit;
- `app/services/effect_analysis.py`: immutable evaluaties met brondekking en confidencefactoren;
- `app/core/queue.py` en `app/scheduler.py`: begrensde queues, retries en periodiek werk;
- `app/services/retention_policy.py`: expliciete bewaartermijnen per dataset;
- API-routes: website- en clienttoegang wordt vóór uitlezen of muteren gecontroleerd.

## 3. Wat al aanwezig is

| Behoefte | Bestaande basis | Conclusie |
|---|---|---|
| Eigen zoekperformance | GSC- en Bing-query/page metrics | Primair houden |
| Gedrag en conversie | GA4 en Matomo | Niet vervangen door externe schattingen |
| Historische URL-context | URL-register, snapshots, changes | Hergebruiken voor trigger en evidence |
| Externe links | Handmatige Bing-linkimport en linkmodellen | Bruikbaar als beperkte bron, niet als volledige dekking |
| Contentcontext | intentie, klantreis, rol, cluster, kansen | Externe data hieraan koppelen |
| Prioriteit | versieerbare opportunity evaluation | Verrijken, geen tweede scoremodel |
| Uitvoering | aanbevelingen, taken, verificaties | Intelligence vertaalt naar dezelfde workflow |
| Effect | interventies en KPI-evaluaties | Later context toevoegen, geen causaliteit |
| Betrouwbaarheid | source coverage, confidence, evidence | Als standaardcontract overnemen |
| Operationeel | queues, retries, dead letters, scheduler | Patronen hergebruiken; betaalde workload isoleren |

Er bestaan nog geen generieke SERP-, keyword-gap-, query-competitor- of externe-provider-modellen.
De roadmap noemt deze richting wel expliciet als specialistische uitbreiding.

## 4. Belangrijkste ontbrekende externe SEO-signalen

Op volgorde van besliswaarde:

1. **SERP-samenstelling bij een bekende belangrijke query**: verklaart lage CTR, positieverlies,
   intent mismatch en veranderde concurrentie.
2. **Pagina-autoriteit ten opzichte van actuele rankingpagina's**: helpt onderscheiden tussen een
   content-, techniek- en autoriteitshypothese.
3. **Ontbrekende onderwerpen binnen een bestaand relevant cluster**: vult alleen gaten aan die GSC
   niet kan zien.
4. **Veranderingen in het competitieve landschap tijdens een interventieperiode**: nuttige latere
   context voor Effect.

Algemene domain scores, alle rankings, alle backlinks en een brede keyworddatabase leveren vooral
dashboardruis en disproportionele kosten op.

## 5. Kritiek op het voorgestelde concept

De richting is productmatig juist, maar de voorgestelde breedte is te groot voor één release.
SERP, backlinks, keyword discovery, content gaps, concurrenten, prioritering en Effect tegelijk
bouwen zou:

- meerdere onbewezen datasets in dezelfde conclusie mengen;
- overlap met bestaande Insights en Content veroorzaken;
- providerkosten en opslag vóór bewezen gebruikerswaarde laten groeien;
- confidence moeilijk uitlegbaar maken;
- een generieke SEO-suite alsnog via de achterdeur introduceren.

De verbetering is één beslisvraag als eerste verticale slice: **waarom presteert een belangrijke
GSC-query of landingspagina anders dan verwacht?** SERP-context kan daarop direct extra bewijs
geven. Backlinks en keyword gaps volgen alleen als deze slice aantoonbaar waarde toevoegt.

## 6. Productprincipes die behouden moeten blijven

- Intelligence is het product; de databron is infrastructuur.
- First-party waarnemingen gaan vóór externe schattingen.
- Externe data verrijkt een bestaande vraag en start niet standaard een nieuw dashboard.
- Waarneming, providerschatting en interpretatie blijven zichtbaar van elkaar gescheiden.
- Iedere conclusie bevat bron, meetmoment, dekking, freshness en confidence.
- Geen totaalscore of causale claim.
- De normale uitkomst is een beter inzicht of taak, niet een grotere tabel.
- Drilldown toont alleen de evidence die nodig is om de conclusie te controleren.

## 7. Verbeterd architectuurvoorstel

Gebruik een kleine capability-adapter, geen universeel providerframework:

```text
bestaand signaal
  -> enrichment policy (relevant, vers genoeg, budget beschikbaar?)
  -> capability adapter (bijv. SERP observation)
  -> genormaliseerde observation + cost record
  -> bestaande Insights/Content/opportunity engine
  -> inzicht, taak of alleen extra evidence
```

Voorgestelde latere bouwblokken:

- `ExternalIntelligenceRequest`: idempotente aanvraag, aanleiding, scope, status en budgetcontext;
- `ExternalObservation`: beperkte genormaliseerde waarneming, provider, observed-at, expiry,
  input-hash en evidence-hash;
- `ExternalUsageRecord`: calls, provider units, geraamde/werkelijke kosten en cache-hit;
- capability-protocols zoals `SerpProvider.fetch_observation(...)` en later
  `AuthorityProvider.fetch_page_context(...)`.

Bewaar geen providerobjecten in businesslogica. Bewaar ook niet standaard ieder volledig raw
response. Een beperkte versleutelde of tijdelijk bewaarde raw fixture kan nodig zijn voor audit en
mapping, maar genormaliseerde observations zijn het productcontract.

## 8. DataForSEO/provider-integratiestrategie

DataForSEO wordt pas gekozen na toetsing op:

- Nederlandse SERP-overeenkomst en locatie-/apparaatondersteuning;
- bruikbare ranking-URL's en SERP-features;
- backlinkdekking voor Nederlandse en internationale verwijzende domeinen;
- voorspelbare kosten per capability en herhaalbaarheid;
- responsekwaliteit, foutgedrag, rate limits en datalicentie;
- mogelijkheid om alleen kleine, gerichte datasets op te vragen.

De eerste adapter ondersteunt precies één capability: een SERP-observation voor één query,
land/regio, taal en apparaat. Een tweede provider wordt niet gebouwd; wel voorkomen het interne
contract en fixtures dat providerstructuren door de kerncode lekken.

## 9. SERP-intelligence

Eerste beslisvragen:

- Wordt lage CTR mede verklaard door dominante SERP-features?
- Verloor een URL positie terwijl de eigen pagina niet relevant veranderde?
- Welke pagina's en domeinen staan nu boven de eigen pagina?
- Past de intentie van de eigen pagina bij het dominante resultaattype?

Minimale observation:

- query, land/regio, taal, apparaat en meetmoment;
- organische posities en ranking-URL's, begrensd tot de relevante topresultaten;
- herkenbare SERP-features en hun plaatsing;
- eigen gevonden URL/positie indien aanwezig;
- genormaliseerde domeinen en afgeleide dominante resultaatintentie;
- provider, freshness en dekkingswaarschuwingen.

Niet opnemen in de eerste versie: dagelijks ranktracken, onbeperkte locaties, volledige SERP-HTML,
screenshots of een algemene rank-history UI.

## 10. Backlink- en autoriteitsintelligence

De bestaande Bing-linkmodellen bewijzen dat linkdata kan worden gekoppeld aan website en
doel-URL. Ze bieden echter geen gegarandeerde volledige dekking en nog geen concurrentvergelijking.

Een latere minimale externe dataset bevat per belangrijke eigen of concurrerende pagina:

- referring-domain count en een beperkte lijst relevante domeinen;
- source domain/URL, target URL, anchor, followstatus indien betrouwbaar;
- eerste en laatste waarneming en nieuw/verloren status;
- bron, meetmoment en coverage-indicatie.

De intelligencevraag staat centraal: heeft een rankingverschil waarschijnlijk een relevante
autoriteitscomponent? Geen algemene domain score, toxicscore of massale backlinkbrowser.

## 11. Concurrentie-intelligence

Concurrentie wordt afgeleid per query, pagina of cluster. `business competitor` blijft optionele
klantcontext; `query competitor`, `page competitor` en `topic competitor` zijn meestal tijdelijke
afleidingen uit observations en hoeven aanvankelijk geen aparte hoofdentiteiten te zijn.

Pas wanneer dezelfde domeinen herhaaldelijk over meerdere relevante observations terugkomen, kan
een gebundelde organische concurrentcontext worden opgeslagen. Daarmee voorkomen we dat een
eenmalige SERP automatisch een strategische concurrent definieert.

## 12. Keyword- en content-intelligence

GSC blijft leidend voor werkelijke eigen impressions, clicks, CTR en positie. Externe keyworddata
is uitsluitend marktcontext voor:

- gerelateerde vragen buiten het huidige GSC-bereik;
- aanvullende formuleringen en onderwerpdekking;
- indicatieve vraag en trend;
- gaps binnen een reeds relevant bevonden cluster.

Een keyword wordt pas een kans na toetsing aan websitecontext, intentie, paginarol, cluster,
businessrelevantie en uitvoerbaarheid. Zoekvolume alleen creëert geen aanbeveling.

## 13. Integratie met bestaande Insights

Externe evidence wordt toegevoegd aan bestaande insight-types:

- CTR-kans: SERP-features als alternatieve verklaring;
- zichtbaarheidverlies: gewijzigde rankingdomeinen of SERP-type;
- queryconflict: actuele eigen en externe ranking-URL's;
- contentkans: aanvullende vraag bevestigd, niet zelfstandig gegenereerd;
- autoriteitshypothese: page-level vergelijking met actuele rankingpagina's.

De insight-engine blijft eigenaar van deduplicatie, formulering en aanbevolen actie. Een adapter
maakt geen gebruikersadvies.

## 14. Integratie met Content

Content gebruikt SERP-context later voor drie gerichte verrijkingen:

- intent mismatch tussen eigen classificatie en dominante SERP-resultaten;
- content gap binnen een bestaand cluster;
- clusterfrictie door externe autoriteit of sterke vaste zoekconcurrenten.

De bestaande classification confidence, overrides en `source_coverage` blijven leidend. Externe
data kan confidence verhogen of verlagen, maar overschrijft geen handmatige override.

## 15. Mogelijke latere integratie met Effect

Effect kan externe observations uit de meetperiode als context tonen, bijvoorbeeld nieuwe
rankingconcurrenten of verloren referring domains. Deze context verandert niet automatisch de
gemeten KPI en bewijst geen oorzaak. Zij beïnvloedt hoogstens een afzonderlijke
`external_context_coverage` en de interpretatie-confidence.

Dit hoort niet in de eerste implementatie: eerst moet observation history stabiel en betaalbaar
zijn en moet duidelijk zijn dat gebruikers deze context nodig hebben.

## 16. Invloed op prioritering

Externe evidence mag aanvankelijk alleen `evidence_score` en verklaarbare contributors beïnvloeden.
Geen nieuwe, losstaande externe SEO-score. Een formulewijziging krijgt een nieuwe versie en de
bestaande immutable `OpportunityEvaluation` bewaart de gebruikte evidence.

Sterke verhoging van prioriteit vereist altijd combinatie met eigen data, bijvoorbeeld relevante
paginarol plus GSC-vraag plus uitvoerbare verbetering. Externe schatting alleen is onvoldoende.

## 17. Nederlandse marktvalidatie

Voer vóór providerkeuze één handmatige, betaalde validatieronde uit met maximaal twaalf vooraf
vastgelegde Nederlandse queries:

- drie landelijke commerciële;
- drie informatieve;
- drie lokale;
- drie long-tail queries;
- verdeeld over desktop en mobiel, zonder iedere query dubbel op te vragen als dat niet nodig is.

Vergelijk SERP, concurrenten en features handmatig met dezelfde locatie- en apparaatcontext. Test
backlinks later afzonderlijk op maximaal drie Nederlandse sites en enkele belangrijke pagina's.
Leg request, genormaliseerde output, expected result, afwijking, bruikbaarheid en kosten vast als
herbruikbare fixture. `API werkt` en `data ondersteunt Nederlandse beslissingen` zijn twee aparte
acceptatiecriteria.

## 18. Kostenmodel en kostenbeheersing

Actuele providerprijzen en contractvoorwaarden zijn nog niet gevalideerd; er wordt daarom nu geen
bedrag per site beloofd. Het toekomstige kostenmodel rekent minimaal:

`requests × prijs per capability + eventuele data-units`, uitgesplitst per client, website,
datatype en aanleiding.

Harde grenzen:

- globale feature flag standaard uit;
- vóór F&F alleen handmatige admin-testcalls;
- maandbudget per site en provider;
- maximum actieve queryscopes;
- idempotency key vóór enqueue;
- budgetreservering vóór call en definitieve usage na response;
- retry mag nooit automatisch een dubbele betaalde aanvraag creëren;
- geen backfill zonder aparte raming en expliciete toestemming.

De grootste kostenrisico's zijn brede periodieke SERP-monitoring, backlinkhistorie en keyword
discovery over grote domeinen. Deze blijven buiten de eerste productie-scope.

## 19. Cache, freshness en event-driven strategie

Startwaarden die na validatie configureerbaar worden:

| Datatype | Richtwaarde freshness | Trigger |
|---|---:|---|
| SERP-context | 7 dagen; 1–3 dagen bij actief incident | bestaand belangrijk inzicht of handmatige verdieping |
| Keywordmarktcontext | 30–90 dagen | gevalideerde contentkans/clusteranalyse |
| Page authority/backlinks | 14–30 dagen | autoriteitshypothese voor belangrijke pagina |
| Concurrentclassificatie | afgeleid uit verse observations | geen losse provider-call |

De cachelookup gebeurt vóór queue-admission. Een verlopen observation blijft zichtbaar als `stale`
en kan nog als historische context dienen, maar niet als actueel bewijs. Schedulerwerk mag vanaf
F&F alleen verse data vernieuwen voor actieve, prioritaire scopes binnen budget; al het overige is
event-driven of on-demand.

## 20. Privacy, security en tenantisolatie

- Iedere request, observation en usage-record draagt `client_id` of een afdwingbaar afleidbare
  `website_id`.
- Alle API-routes gebruiken bestaande client-/websiteautorisatie; betaalde triggers vereisen
  schrijftoegang en aanvankelijk adminrechten.
- Providercredentials blijven centraal versleuteld/configured en nooit per taskpayload of log.
- Logs bevatten request-id, capability, website-id, units en status, geen secrets of volledige raw
  payloads.
- Query's kunnen klant- of marktinformatie bevatten; retentie en exports moeten dit expliciet
  behandelen.
- Raw responses krijgen een korte, gemotiveerde retentie; genormaliseerde evidence en usage-audit
  volgen een afzonderlijk beleid.
- Een providerrequest bevat alleen de minimale query, URL, locatie en apparaatcontext.

## 21. Pareto-versie voor eerste implementatie

Eén verticale slice:

> Verrijk een bestaande belangrijke GSC CTR- of zichtbaarheidskans op verzoek met één verse
> Nederlandse SERP-observation en toon de extra evidence in hetzelfde inzicht.

Acceptatie:

- zonder provider of budget blijft het bestaande inzicht ongewijzigd werken;
- dezelfde context binnen de freshnessperiode veroorzaakt geen nieuwe betaalde call;
- bron, meetmoment, locatie, apparaat, features en rankingconcurrenten zijn controleerbaar;
- de conclusie onderscheidt eigen data, externe observation en interpretatie;
- retry en dubbel klikken veroorzaken maximaal één providerrequest;
- er ontstaat geen los SERP-dashboard.

## 22. Concrete roadmapplaats

De bestaande roadmapsectie **SERP-, zichtbaarheid- en concurrentieanalyse** blijft de juiste plek,
maar wordt opgesplitst:

- vóór F&F-readiness: analyse, capability-contract, mocks, fixtures, budgetguard en Nederlandse
  testopzet;
- beperkte betaalde test: apart go/no-go-moment na actuele prijscontrole;
- vanaf F&F: de SERP-slice alleen voor geselecteerde sites/queries activeren;
- na bewezen waarde: page-authoritycontext;
- later: clustergebonden keyword/content gaps en competitieve historie;
- nog later: optionele Effect-context.

Deze richting verandert Release 11 niet en rechtvaardigt geen onderbreking van de huidige
readiness- en kwaliteitsgates.

## 23. Afhankelijkheden

- stabiele GSC-querydata en bestaande Insights-selectie;
- duidelijke definitie van `belangrijke query/pagina`;
- providervergelijking en actuele prijsinformatie;
- Nederlandse validatieset en handmatige expected results;
- budget- en usagecontract vóór echte calls;
- retentiebeleid voor raw en normalized external data;
- queue-isolatie en workerrechten vóór productieactivatie;
- productkeuze welke klanten/sites tijdens F&F toegang krijgen.

## 24. Fasering

### Nu analyseren — gereed met dit document

- bestaande datastromen en overlap vaststellen;
- Pareto-use-case en architectuurgrenzen bepalen;
- roadmapplaats en open besluiten vastleggen.

### Vóór F&F voorbereiden — geen structurele kosten

- capability-contract, normalized schema en fixtures;
- fake provider en tests voor cache, idempotency, budget en tenanttoegang;
- handmatige validatieroute en usage-audit;
- geen scheduler en feature flag uit.

### Beperkte betaalde test toegestaan — apart besluit

- actuele provider/callprijs controleren;
- maximaal twaalf SERP-queries ophalen en één keer vastleggen;
- alleen bij voldoende kwaliteit later maximaal drie backlinkcases testen;
- kosten en kwaliteit evalueren; providerkeuze daarna pas vastleggen.

### Pas vanaf F&F activeren

- SERP-enrichment voor geselecteerde belangrijke inzichten;
- harde sitebudgetten, cache en operationele monitoring;
- alleen expliciet geselecteerde tenants.

### Later

- page-level autoriteitsvergelijking;
- clustergebonden keyword- en content gaps;
- competitieve historie en externe Effect-context.

## 25. Bewust niet bouwen

- generiek DataForSEO-dashboard;
- algemene domain- of SEO-score;
- volledige backlink explorer of toxic-linkscore;
- brede keyworddatabase of onbeperkte keyword discovery;
- dagelijks alle rankings, concurrenten of backlinks verversen;
- automatische bedrijfsconcurrenten afleiden uit één SERP;
- providerobjecten in insights, tasks of opportunity scoring;
- externe schattingen die GSC, Bing, analytics of crawlerwaarnemingen overschrijven;
- causale Effect-conclusies op basis van gelijktijdige externe veranderingen;
- facturatie- of abonnementsframework vóórdat pricing dit vereist.

## 26. Relevante bestaande en nieuw geraakte bestanden/modules

### Bestaand hergebruiken

- `app/models/integrations.py`
- `app/models/opportunities.py`
- `app/models/content_analysis.py`
- `app/models/effects.py`
- `app/models/website.py`
- `app/services/consultant_insights.py`
- `app/services/content_analysis.py`
- `app/services/opportunity_engine.py`
- `app/services/opportunity_scoring.py`
- `app/services/effect_analysis.py`
- `app/core/queue.py`
- `app/scheduler.py`
- `app/services/retention_policy.py`
- bestaande autorisatie-, audit- en dead-letterservices

### Waarschijnlijk nieuw bij een latere implementatie

- `app/models/external_intelligence.py`
- `app/schemas/external_intelligence.py`
- `app/services/external_intelligence/policy.py`
- `app/services/external_intelligence/serp.py`
- `app/services/external_intelligence/providers/base.py`
- één concrete provideradapter na het go/no-go-besluit;
- Alembic-migratie, fixture-gebaseerde tests en een beperkte adminroute;
- configuratie voor feature flag, budget en credentialreferentie.

Dit zijn voorgestelde grenzen, geen opdracht om deze bestanden nu aan te maken.

## 27. Open beslispunten

1. Welke bestaande insight-types mogen de eerste SERP-enrichment aanvragen en met welke drempel?
2. Is de eerste F&F-scope handmatig per query of automatisch voor maximaal een klein aantal
   hoogst geprioriteerde queries?
3. Welke provider wint na actuele prijs-, licentie- en Nederlandse kwaliteitstoets?
4. Welke raw response moet tijdelijk worden bewaard voor audit en debugging?
5. Welk maandbudget en welke harde querylimiet gelden per F&F-site?
6. Wanneer is Bing-linkdata voldoende evidence en wanneer is een externe backlinkcall nodig?
7. Welke externe context mag opportunity confidence wijzigen en welke blijft alleen toelichting?

## Besluit

Ga niet breed bouwen. Bereid vóór F&F één provider-onafhankelijke SERP-slice voor, valideer deze
met fixtures en pas daarna met een klein betaald Nederlands testpakket. Activeer structurele calls
pas vanaf F&F, per geselecteerde site en binnen harde budgetten. Autoriteit, keyword gaps en Effect
volgen alleen na aantoonbare gebruikerswaarde.

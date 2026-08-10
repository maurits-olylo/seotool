# Release 13 — Thactual Sensor architecture discovery

Status: fasen A tot en met F lokaal en op staging geaccepteerd. Er is geen publieke ingestion of
Matomo-productiedeployment.

## 1. Executive summary

Thactual heeft geen nieuw analyticsproduct nodig. Het heeft een kleine, controleerbare
observatielaag nodig die URL-gebonden gedrags- en outcome-evidence levert aan de bestaande keten
`inzicht → kans → actie → verificatie → effect`.

De huidige codebase ondersteunt al dagelijkse, aan het URL-register gekoppelde totalen uit GA4 en
Matomo. De abstractie is echter smal: zij normaliseert alleen bezoeken, gebruikers en conversies.
Sessies, events, process states, exposure, trust, manifests en measurement provenance bestaan nog
niet als provider-onafhankelijke concepten. Verscheidene rapportage- en analysestraten lezen nog
rechtstreeks uit GA4- of Matomo-tabellen.

### Advies

Start niet direct met de volledige voorkeursoptie C. Kies voor de F&F-pilot een begrensde variant
van **optie A**:

1. een centraal, EU-gehost Matomo als tijdelijke behavioral processing- en aggregatie-engine;
2. de volwassen Matomo JavaScripttracker, strikt geconfigureerd via één kleine Thactual-bootstrap;
3. een eigen, versieerbaar Thactual observation manifest en canonical observation vocabulary;
4. uitsluitend page/session, active time, primaire element-exposure, primaire interactie,
   process start en process success;
5. dagelijkse, URL-gebonden Sensor-aggregaten in Thactual; geen raw-eventkopie;
6. server-confirmed outcomes later via een afzonderlijk vertrouwd endpoint.

Deze keuze behoudt producteigenaarschap over semantiek zonder meteen batching, retries,
sessionization, SPA-afhandeling, consenthooks, botfiltering en archive processing opnieuw te bouwen.
Ga pas naar optie C wanneer de pilot aantoont dat `matomo.js` het performancebudget overschrijdt,
het manifest niet betrouwbaar kan uitvoeren of Matomo-events de benodigde observation semantics
niet zuiver kunnen representeren.

## 2. Current architecture

De actuele datastroom is pull-gebaseerd:

```text
GSC / Bing / GA4 / extern Matomo
        ↓ periodieke integration-worker
provider-specifieke dagelijkse tabellen
        ↓ gedeeltelijke analytics abstraction
URL-gebonden totalen en quality status
        ↓
inzichten / opportunities / taken / effectevaluaties

crawler → snapshots → issues ─┐
renderer → renderbewijs ──────┼→ dezelfde verbeterworkflow
accessibility → issues ───────┘
```

Er is geen client-side Thactual-meetlaag, publiek ingestionendpoint, observation manifest,
Sensor-sessionmodel of Thactual-owned behavioral eventstore.

## 3. Relevant existing code

| Onderdeel | Bestaand | Betekenis voor Sensor |
|---|---|---|
| `app/models/discovery.py` | blijvende `Url`-identiteit | canonical koppelpunt voor aggregaten |
| `app/services/url_normalization.py` | gedeelde URL-normalisatie | hergebruiken vóór URL-matching |
| `app/models/integrations.py` | provider-specifieke dagmetrics | behouden voor legacy/import; niet uitbreiden tot Sensor-events |
| `app/services/analytics_provider.py` | bezoeken/gebruikers/conversies per URL | concept hergebruiken, contract verbreden |
| `app/services/analytics_journey.py` | providerselectie en journey-evidence | ombouwen naar capabilities, niet providerbranches |
| `app/services/analytics_quality.py` | anomalieën en twee-schone-checks | lifecycle hergebruiken voor measurement quality |
| `app/models/opportunities.py` | historische opportunities met coverage/evidence | Sensor wordt contributor, niet zelfstandig issue |
| `app/models/effects.py` | interventies en effectcohorten | Sensor-aggregaten kunnen observationmetrics leveren |
| `app/services/render_executor.py` | begrensde browserwaarneming | bron voor manifestkandidaten en selectorcontrole |
| `app/core/queue.py` | RQ-policy, retries, dead letters | bruikbaar voor archivering/import, niet voor request-path ingestion |
| `app/services/privacy_deletions.py` | verwijderledger per klant/website | uitbreiden naar Sensor/Matomo-verwijdering |

## 4. Existing GA4 implementation

GA4 wordt via de Data API periodiek opgehaald. Thactual bewaart dagelijkse organische
landingspagina-totalen, eventtotalen en gekwalificeerde events per landingspagina. De gebruiker
selecteert expliciet gekwalificeerde events.

Sterk:

- OAuth-, tenant- en propertyscope bestaan;
- URL-koppeling en historische import bestaan;
- geselecteerde events voorkomen dat alle GA4-key events automatisch businessoutcomes worden;
- anomalieën zoals events zonder aannemelijke sessies krijgen een normale issue-lifecycle.

Beperkt:

- geen element-exposure, process progression of server-confirmed outcome;
- `GoogleAnalyticsMetric` wordt rechtstreeks gelezen in onder meer rapportage, indexatie en
  interne-linkanalyse;
- de opgeslagen metrics zijn landingspagina-centric, niet een algemeen observationmodel;
- definities en implementatiekwaliteit blijven afhankelijk van de GA4-configuratie van de klant.

GA4 blijft legacy/historical import en een tijdelijke validatiebron, niet de standaard Sensor.

## 5. Existing Matomo implementation

De huidige Matomo-integratie beheert een externe HTTPS-server, versleuteld API-token, siteselectie
en Reporting API-import. Zij haalt pagina-, referrer-, goal- en conversionaggregaten op en bewaart
die in `MatomoPageMetric` en `MatomoAggregateMetric`.

Sterk:

- server-URL-validatie, SSRF-controle, geen redirects en veilige foutmeldingen;
- site- en tenantscope;
- URL-koppeling, dagelijkse aggregaten en historische import;
- entry visits, bounces, exits en conversies zijn beschikbaar voor journey-frictie;
- Matomo en GA4 worden nooit opgeteld.

Beperkt:

- Thactual installeert of configureert nu geen tracker;
- geen Tracking API-adapter of Thactual-owned Matomo bestaat;
- events, content impressions, custom dimensions en goals hebben nog geen canonical mapping;
- echte paginatransities worden niet geïmporteerd;
- Matomo bepaalt impliciet enkele journeyvelden, zoals entry/bounce/exit, buiten de kleine provider-
  abstraction.

## 6. Current provider abstraction

`analytics_page_totals_between()` levert één `AnalyticsPageTotal` met `visits`, `users` en
`conversions`. Dit is bruikbaar voor prioritering, maar geen volledige provider abstraction.

Provider-independent:

- primaire bron per website;
- URL-gebonden periode-totalen;
- quality-aware totals;
- coverage als evidence;
- opportunity- en effectconsumenten die alleen deze totalen gebruiken.

Nog provider-specific:

- reports kiest concrete SQLAlchemy-modellen en kolommen;
- journey bouwt aparte GA4- en Matomoqueries;
- analytics quality heeft aparte anomaliedetectors;
- effect analysis kiest per provider concrete tabellen;
- interne-link- en indexatieanalyse lezen op plaatsen alleen GA4;
- onboarding kent nog geen capability- of measurement-profilecontract.

Sensor mag daarom niet als derde `elif source == "sensor"` door alle modules worden verspreid.

## 7. Sensor requirements and product boundary

Sensor neemt waar; Thactual interpreteert. De browserlaag mag alleen vooraf toegestane technische
observaties produceren. Businessbetekenis, prioriteit en issuevorming blijven server-side.

De pilot ondersteunt:

- page observation;
- tijdelijke session context;
- lokaal geaccumuleerde active time;
- exposure van maximaal enkele manifest-elementen;
- interaction met die elementen;
- process start en process success;
- measurement heartbeat/configuration status.

Niet in de pilot: attribution, persistent profiel, cross-session journey, replay, heatmaps,
autocapture, generiek formulierinhoud, advertentiedoeleinden of analyticsdashboard.

### Canonical sources per type werkelijkheid

- crawler en renderer: technische en gerenderde websitetoestand;
- accessibility-engine: genormaliseerd toegankelijkheidsbewijs;
- Google Search Console: Google-zoekvraag, vertoning, klik, CTR en positie;
- Bing Webmaster Tools: Bing-zoek- en backlinkbewijs;
- Sensor: websitegedrag en outcomes;
- externe intelligence: markt-, SERP-, concurrentie- en citationcontext.

GSC en Bing worden niet door Sensor vervangen. Het URL-register blijft de verbindende identiteit.
Crawler en renderer kunnen manifestkandidaten leveren, maar bepalen geen bezoekersgedrag.

## 8. Persistent visitor identity

Geen bestaande productfunctie vereist herkenning over meerdere sessies of websites. Opportunity-
en effectlogica werken op URL × periode-aggregaten. Een blijvende visitor-ID voegt daarom privacy-
en consentcomplexiteit toe zonder huidige besliswaarde.

Gebruik hoogstens een tijdelijke, niet-herleidbare session identifier wanneer dit na juridische en
methodologische toetsing nodig blijkt. Behandel browserstorage daarbij als trackingtechnologie; first
party of cookieless betekent niet automatisch toestemmingsvrij.

## 9. Option A — Matomo client and backend

```text
website → Thactual bootstrap → matomo.js → Matomo Tracking API
        → Matomo archive/reporting → Sensor aggregate adapter → Thactual
```

De bootstrap laadt siteconfiguratie, consentstatus en manifest en vertaalt alleen toegestane
observaties naar gebatchte Matomo-events. De eerste stagingmeting wees pageviews en directe events
af omdat zij de requestqueue omzeilden; de adapter gebruikt daarom Matomo's publieke
`queueRequest`-interface en laat Matomo bezoek- en URL-context toevoegen.

Voordelen:

- volwassen batching/requestgedrag, sessionization, SPA-hooks, consentfuncties en heartbeat;
- sluit direct aan op de al aanwezige Reporting API-import;
- laagste nieuwe operationele en securityscope;
- snelste manier om observation value en volume te meten.

Nadelen:

- de browserclient bevat meer generieke functionaliteit dan Sensor nodig heeft;
- eigen semantics moeten zorgvuldig in events/dimensions worden gemapt;
- performancebudget moet empirisch worden bewaakt;
- direct Matomo-ingestion biedt minder centrale payloadcontrole;
- server-confirmed outcomes vereisen alsnog een vertrouwd pad.

## 10. Option B — fully custom client and backend

```text
website → sensor.js → Sensor ingestion → raw/operational store
        → session/event processing → aggregates → Thactual
```

Deze optie levert maximale controle, maar vereist vrijwel alle moeilijkheden die de prompt juist wil
vermijden: publieke ingestion, retries, deduplicatie, ordering, sessionization, bots, abuse, schema-
migratie, archivering, backfill, privacyverwijdering en operationele monitoring.

De bestaande PostgreSQL/RQ-stack is geschikt voor achtergrondtaken, maar RQ is geen
hoogfrequente ingestionbus. Requests eerst in Redis/RQ plaatsen introduceert verlies- en
backpressurevragen; synchroon naar PostgreSQL schrijven vergroot databasebelasting en cardinaliteit.

Optie B is niet verantwoord voor F&F.

## 11. Option C — custom client and ingestion with Matomo backend

```text
website → sensor.js → Sensor validation/normalization → Matomo Tracking API
        → Matomo archive/reporting → Sensor aggregate adapter → Thactual
```

Voordelen:

- canonical schema en payloadcontrole aan de rand;
- centrale tenant/sitevalidatie, PII-rejectie, quotas en trusted-outcome-scheiding;
- Matomo blijft vervangbare processingadapter;
- custom client kan uiteindelijk kleiner zijn.

Nadelen:

- twee nieuwe runtimecomponenten vóór een bestaand backend;
- Sensor moet browsersemantiek naar Matomosemantiek vertalen én sessiecontext correct bewaren;
- proxyfouten en Matomofouten krijgen eigen retry- en deduplicatielogica;
- latency, observability, security en deployscope nemen toe;
- het huidige platform bezit nog geen ingestionfundament waarop dit eenvoudig landt.

Optie C is een zinvolle doelarchitectuur, maar niet de kleinste betrouwbare eerste pilot.

## 12. Comparison matrix

| Criterium | A: Matomo client | B: volledig eigen | C: eigen client + Matomo |
|---|---|---|---|
| Productfit | goed met eigen manifest | uitstekend | uitstekend |
| Development effort | laag–middel | zeer hoog | hoog |
| Operational effort | middel | zeer hoog | hoog |
| Client performance | te meten; generiek | potentieel best | potentieel best |
| Backend performance | volwassen | volledig eigen risico | volwassen core, extra hop |
| Privacy control | goed configureerbaar | maximaal | zeer goed |
| EU-beheerbaarheid | goed bij eigen EU-host | volledig eigen | goed, meer componenten |
| Event flexibility | goed | maximaal | zeer goed |
| Outcome measurement | goed; trusted pad apart | volledig eigen | zeer goed |
| Element exposure | gebatcht canonical event | volledig eigen | volledig eigen |
| Form/process tracking | goed met allowlist | volledig eigen | zeer goed |
| SPA support | volwassen | zelf bouwen | zelf bouwen |
| First-party support | proxy/config nodig | native | native |
| Anti-abuse | Matomo + edge | zelf bouwen | eigen randcontrole |
| Reliability | volwassen | onbekend | gedeeld verantwoordelijk |
| Measurement quality | bewezen basis + eigen checks | volledig zelf | eigen + Matomo |
| Matomo lock-in | middel | geen | laag bij goede adapter |
| Migration complexity | laag | hoog | middel–hoog |
| F&F suitability | beste | ongeschikt | alleen na foundation |
| Custom code | beperkt | maximaal | aanzienlijk |
| Technisch risico | laagst | hoogst | middel–hoog |
| Onderhoudbaarheid | goed bij strakke mapping | onzeker | goed na hogere startkosten |

Een gewogen totaalscore voegt hier geen waarheid toe. De doorslag voor F&F is dat optie A de
meeste onzekere onderdelen observeerbaar maakt voordat Thactual ze zelf bouwt.

## 13. Matomo Tracking API fit

De officiële Tracking API ondersteunt pageviews, events, custom dimensions, goals, visitcontext en
bulk POST. Een visitor-ID is aanbevolen voor nauwkeurige unieke bezoekers en sessiekoppeling, maar
Thactual heeft geen blijvende visitoridentiteit nodig. Dat betekent dat unieke-bezoekerstatistiek
bewust minder belangrijk wordt of dat alleen een tijdelijke sessiecontext wordt gebruikt.

Bulk tracking vereist chronologische requests en maakt een server-side adapter efficiënt, maar is
geen gratis queue: ordering, retry en deduplicatie blijven bij Sensor wanneer optie C wordt gekozen.

Bronnen:

- [Matomo Tracking HTTP API](https://developer.matomo.org/api-reference/tracking-api)
- [Matomo JavaScript tracking guide](https://developer.matomo.org/guides/tracking-javascript-guide)
- [Matomo cookieless implications](https://matomo.org/faq/general/faq_156/)

## 14. Recommended client runtime design

Voor de pilot is `sensor-bootstrap.js` configuratie, niet een nieuwe tracker. Verantwoordelijkheden:

1. site-bound configuratie ophalen of inline ontvangen;
2. schema-, client- en manifestversie valideren;
3. consent/privacyprofiel toepassen vóór tracking;
4. Matomo tracker asynchroon laden;
5. alleen manifest-observaties registreren;
6. geen formulierwaarden of vrije tekst lezen;
7. client performance en measurement status samenvatten.

Bij doorgroei naar C kan dezelfde publieke API behouden blijven en verandert alleen de interne
transportadapter.

## 15. Observation manifest

Canonical voorbeeld:

```json
{
  "schema_version": "1",
  "manifest_version": "2026-08-10.1",
  "site_key": "public-site-bound-id",
  "profile": "lead_generation",
  "page_match": "/offerte",
  "observations": [
    {"key": "primary_cta", "kind": "exposure", "locator": "stable-logical-id"},
    {"key": "quote_form", "kind": "process", "locator": "stable-logical-id"}
  ],
  "expires_at": "2026-09-10T00:00:00Z"
}
```

De renderer mag kandidaten vinden, maar publiceert nooit autonoom iedere selector. Alleen stabiele,
begrensde locators worden na expliciete configuratie actief. Gebruik bij voorkeur door de klant of
plugin geplaatste `data-thactual`-identifiers. CSS-paden uit screenshots zijn bewijs, geen stabiel
trackingcontract.

Bij ontbrekend of verlopen manifest: alleen measurement status, geen generieke autocapture.

## 16. Canonical event schema

```json
{
  "schema_version": "1",
  "client_version": "1.0.0",
  "manifest_version": "2026-08-10.1",
  "site_key": "public-site-bound-id",
  "session_key": "ephemeral-value",
  "page_url": "https://example.test/offerte",
  "observed_at": "2026-08-10T12:00:00Z",
  "name": "process_success",
  "subject": "quote_form",
  "value": {"duration_bucket": "30_60s"},
  "trust": "browser",
  "priority": "critical"
}
```

Allowlist `name`, `subject` en iedere value-key. Querystrings worden vóór verzending volgens het
websitebeleid verwijderd. Geen DOM-tekst, veldwaarde, e-mail, telefoonnummer, user-ID, IP-adres of
vrije fouttekst in het schema.

## 17. Element exposure

Element exposure levert meer besliswaarde dan generieke scroll depth. Registreer alleen wanneer een
manifest-element minimaal een afgesproken deel van de viewport gedurende een korte minimumduur
zichtbaar was. Gebruik `IntersectionObserver`; geen scrollhandler of permanente polling.

Aggregeer per URL/periode:

- sessions with page;
- sessions exposed;
- sessions interacted;
- sessions with trusted/observed outcome.

Daarmee kan Thactual voorzichtig onderscheiden: niet bereikt, gezien maar niet gebruikt, gebruikt
maar geen gemeten outcome. Geen van deze uitkomsten bewijst zelfstandig de oorzaak.

## 18. Active time and content consumption

Matomo heartbeat verbetert bezoekduur, maar volgens de officiële documentatie niet automatisch de
gemiddelde tijd op paginaniveau en lost multi-tab-attributie niet op. Sensor mag daarom geen
schijnprecisie uit heartbeat afleiden.

Voor de pilot:

- zichtbaar document;
- focus;
- recente inputactiviteit in een ruim window;
- lokaal accumuleren;
- één samenvatting bij pagehide/routewissel en optioneel één begrensde tussentijdse flush;
- opslaan in grove buckets, niet milliseconden.

Expected reading time is alleen ondersteunend bewijs naast paginarol, exposure, vervolgstap en
outcome.

## 19. Scroll progression

Gebruik alleen 25/50/75 procent als fallback voor contentprofielen zonder stabiele elementen.
Voorkeur: semantische exposure zoals artikelkern, CTA of formulier. Verschillende layouts maken een
universeel scrollpercentage methodologisch zwak.

## 20. Process, conversion and abandonment

Modelleer technische states:

```text
process_seen → process_start → process_progress? → process_error? → process_success
```

`abandonment` is een server-side afleiding: start zonder success binnen dezelfde geldige tijdelijke
sessie/window. Bewaar de afleiding, methode en volledigheid; genereer niet automatisch een issue.

Outcome strength:

1. server-confirmed success;
2. expliciet application event;
3. allowlisted dataLayer event;
4. stabiele success state;
5. unieke thank-you URL;
6. click proxy.

Browserobservations krijgen nooit dezelfde trust als een ondertekend serverevent.

## 21. Dynamic and third-party forms

Cross-origin iframes zijn niet generiek observeerbaar. Ondersteun per integratie één expliciet pad:
providerwebhook/serverevent, allowlisted `postMessage`, dataLayer, thank-you URL of alleen een zwakke
clickproxy. De interface moet ontbrekend bewijs tonen en geen automatische complete meting beloven.

## 22. Measurement quality

Introduceer later `SensorMeasurementState` per website en periode, niet een generieke score:

- status: `not_configured`, `provisional`, `reliable`, `attention_needed`, `stale`;
- client-, schema- en manifestversie;
- first/last observation;
- expected versus observed page coverage;
- rejected/sampled counts;
- outcome evidence mix;
- configuration change timestamps;
- freshness en maturity;
- laatste twee schone controles.

Hergebruik de bestaande analytics-quality lifecycle en activity logging. Nieuwe controles zijn
onder meer plotseling nulverkeer, manifest/client mismatch, onmogelijke outcome/startverhouding,
cardinalitygroei en langdurig ontbrekende heartbeat.

## 23. Data model and ownership

### Kan blijven

- `Url`, `Website`, `WebsiteSettings`;
- `IntegrationConnection`/`WebsiteIntegration` voor legacybronnen;
- `OpportunityEvaluation`, `EffectIntervention`, `EffectEvaluation`;
- issues, occurrences, activity log en taakworkflow.

### Kleine foundation

- provider capabilitycontract naast `AnalyticsPageTotal`;
- `sensor_measurement_states`;
- `sensor_daily_page_metrics` met page sessions, active-time buckets, exposure/interactions en
  observed/trusted outcomes;
- `sensor_outcome_definitions` met businessbetekenis, evidence-eis en ingangsdatum;
- `sensor_manifests` met versie, hash, status en geldigheidsperiode.

### Niet in Thactual dupliceren

- volledige raw eventstream;
- visitorprofielen;
- Matomo visits log;
- volledige device/referrer/audiencekubus.

Matomo bewaart operationele/raw behavioral data kort; Thactual bewaart alleen dagelijkse URL-
aggregaten, outcome meaning, provenance, confidence en effectevidence.

## 24. Provider and adapter design

Vervang providerbranches stapsgewijs door capabilities:

```python
BehavioralCapabilities(
    page_sessions=True,
    outcomes=True,
    entrance=True,
    continuation=False,
    element_exposure=False,
    process_states=False,
    trusted_outcomes=False,
)
```

Een `BehavioralAggregateProvider` levert canonical dagaggregaten. Adapters:

- `Ga4AggregateAdapter` — legacy;
- `MatomoReportingAdapter` — legacy en Sensor-pilot;
- later `SensorAggregateAdapter` — wanneer C gerechtvaardigd is.

Businesslogica leest capabilities en coverage, nooit Matomo event category/action/names.

## 25. First-party architecture

Een **Thactual Gateway** op dezelfde origin als de gemeten website is een harde voorwaarde voor de
Sensor-pilot. Een CNAME of analytics-subdomein is first-party in sommige cookiedefinities, maar is
niet same-origin en kan nog steeds als bekende trackingroute worden behandeld. De browser mag
daarom uitsluitend lokale paden zien, bijvoorbeeld:

```text
https://www.example.com/thactual/sensor.js
https://www.example.com/thactual/observe
```

De Gateway levert het gepinde script en stuurt toegestane observations server-side door naar de
EU Sensor/Matomo-backend. Matomo-hostnamen, eventnamen en credentials worden nooit onderdeel van
de publieke installatie. Een eventuele cookie wordt uitsluitend host-only op de website-origin
gezet; de standaard blijft cookieless zonder persistent visitor-ID.

Het installatiecontract is voor iedere ondersteunde stack gelijk:

1. installeer één Thactual-plugin, app of beheerde reverse-proxymodule;
2. koppel de website met een eenmalige sitegebonden autorisatie;
3. laat Thactual scriptpad, observationpad, forwarding, caching en consentconfiguratie aanmaken;
4. rond af met één automatische live verificatie.

De installatietest slaagt alleen wanneer script en observations exact via de website-origin lopen,
geen third-party browserrequest ontstaat, forwarding werkt en caching, batching en deduplicatie
correct zijn. Handmatige Matomo-eventconfiguratie per pagina is niet toegestaan.

Dit contract schermt de meetengine af: een latere overgang van optie A naar C verandert de
klantinstallatie niet. Per stack mag de implementatie verschillen, maar maatwerk per klant is geen
acceptabele standaardroute. Begin met één volledig ondersteunde stack; voeg een volgende stack pas
toe met dezelfde automatische installatie- en verificatietest.

De garantie geldt voor browserclassificatie volgens het same-originmodel. Geen product kan
garanderen dat iedere extensie, filterlijst of beveiligingsoplossing een first-party pad nooit
blokkeert. Een first-party route verandert browsertrust bovendien niet in servertrust; forwarding
blijft onder het anti-abusecontract vallen.

## 26. Anti-abuse and trust

Voor iedere publieke route:

- public site-bound key, nooit een secret in JavaScript;
- bekende site/domainbinding;
- strikte schema- en eventallowlist;
- maximale batch-, event-, string- en payloadgrootte;
- rate limit en dagquota per site/IP-signaal;
- cardinalitylimiet per subject/manifest;
- timestampwindow en replay/dedup-id;
- geen vertrouwd outcome via browsercredential;
- veilige logging zonder payloadinhoud;
- rejected-eventmetric en anomaly alert.

Trusted outcomes gebruiken een afzonderlijk servercredential, tenant/site scope, signature,
timestamp en replaybescherming.

## 27. Privacy, consent and jurisdiction

Cookieless, first-party en IP-anonimisering zijn privacymaatregelen, geen automatische juridische
vrijstelling. Matomo vermeldt zelf dat in diverse Europese rechtsgebieden ook JavaScriptanalytics
voorafgaande toestemming kan vereisen.

Daarom:

- standaard geen persistent ID, geo of volledige referrer/query;
- privacyprofiel per website met versie en beoordelingsdatum;
- consentmode expliciet en testbaar;
- IP niet doorgeven aan Thactual en in Matomo passend anonimiseren;
- korte raw retention en aantoonbare deletion/backup propagation;
- geen cross-site/cross-client identity;
- landprofielen pas toevoegen wanneer een concrete doelmarkt dat vereist.

Bron: [Matomo consent guidance](https://matomo.org/faq/general/do-i-need-consent-to-use-web-analytics-on-my-website/).

## 28. Heartbeat relation

Splits twee concepten:

- browser active-time summary: evidence over gebruik;
- server-side availability check: context bij verkeersverandering.

Availability hoort niet in `sensor.js`. Hergebruik later crawler-HTTP-beveiliging en een zeer
begrensde schedulerjob. Alleen ernstige of herhaalde downtime kan een insight worden; anders is het
een annotatie bij dalingen en effectvensters.

## 29. Performance budget

Pilotgate per representatieve mobiele pagina:

- bootstrap plus gepinde Matomo-client maximaal 50 KB gecomprimeerd op eerste bezoek;
- Sensor-uitvoering maximaal 25 ms totale main-threadtijd;
- maximaal één initiële trackingrequest plus één gebatchte vervolgrequest in de normale flow;
- maximaal 10 KB observationpayload per normale sessie;
- geen permanente polling of generieke MutationObserver;
- maximaal één IntersectionObserver per pagina;
- geen long task van 50 ms of meer toe te schrijven aan Sensor;
- p75 INP-verslechtering maximaal 10 ms en maximaal 5 procent;
- p75 LCP-verslechtering maximaal 50 ms en CLS-delta maximaal 0,001;
- main-threadtijd, geheugen, requestcount en bytes als releasebewijs bewaren;
- minimaal 99 procent aflevering van verplichte observations in de gecontroleerde proef;
- minder dan 0,5 procent duplicaten en minimaal 98 procent succesvolle manifest-/elementkoppeling.

Beoordeel deze grenzen met reproduceerbare vergelijkingen op representatieve pagina's en apparaten,
niet met één Lighthouse-run. Gebruik voor de pilot minimaal twintig vergelijkende labruns en daarna
twee weken veldmetingen; de p75 is leidend. Een herhaalde harde overschrijding na normale
optimalisatie blokkeert uitbreiding van de pilot.

Een eigen client mag pas als “lichter” worden aangemerkt na dezelfde reproduceerbare meting tegen
de gekozen Matomo-configuratie.

De repository bevat nu geen gepinde `matomo.js`-asset of eigen trackingconfiguratie. De werkelijke
scriptgrootte en runtimeoverhead zijn daarom nog onbekend en mogen niet uit algemene Matomo-cijfers
worden afgeleid. De eerste spike moet beide artifacts exact bouwen, meten en archiveren.

## 30. Event priority and graceful degradation

- Critical: trusted/observed success, expliciete process error.
- Important: page/session, process start, primaire interaction.
- Optional: active-time update, scroll, exposure, repeated interaction.

Bij overload worden eerst optional observations gesampled of geweigerd. Critical events krijgen
een eigen klein quotum, maar blijven onder dezelfde payload- en anti-abusegrenzen.

## 31. Redis/RQ and ingestion

RQ blijft geschikt voor imports, archivering, manifestgeneratie en quality checks. Het publieke
requestpad mag niet afhankelijk zijn van één RQ-job per event. Optie A stuurt direct naar Matomo.
Optie C vereist eerst een duurzame korte buffer of aantoonbaar veilige synchrone forwarding met
idempotency; de bestaande Redis-configuratie met begrensd geheugen en eviction is geen duurzaam
eventlog.

## 32. F&F architecture

De in de prompt genoemde 6-vCPU/16-GiB/200-GB-VPS is **beoogd en niet operationeel bevestigd**. De
canoniek vastgelegde bestaande VPS heeft lagere capaciteit. Voer voor inzet opnieuw een read-only
capaciteitsmeting uit.

Voor circa vijftien organisaties:

```text
één EU-host
├─ Thactual API/PostgreSQL/Redis/workers/rendering
├─ Matomo web/archiver
└─ MariaDB voor Matomo

NAS
├─ staging
├─ versleutelde backups
└─ geïsoleerde restoretests
```

Gebruik gescheiden databases, serviceaccounts, volumes, retention en resourcegrenzen. Sensor en
Thactual mogen op één host starten, maar falen en opslaggroei moeten afzonderlijk zichtbaar zijn.

## 33. Capacity and scaling

Meet per site:

- page observations, total observations en outcomes per dag;
- bytes/event, events/session, requests/session en rejectionratio;
- archive latency en dagelijkse aggregate latency;
- Matomo MariaDB-groei en Thactual aggregategroei;
- CPU, RAM, I/O, back-upduur en restoreduur;
- clientbytes, execution time, long tasks en Core Web Vitals-delta.

Splits pas een Sensor- of Matomo-node af wanneer deze metrics aantonen welk onderdeel de grens
bereikt. Geen Kafka, Kubernetes of distributed database voor F&F.

## 34. Onboarding

Sensor komt na website-eigendomsverificatie. De wizard toont:

1. observation profile;
2. consent/privacyprofiel;
3. installatie-instructie;
4. live measurement verification;
5. outcome mapping en evidence strength;
6. nulmeting en quality status.

Een technische crawl blijft mogelijk zonder Sensor. Behavioral opportunities en effectclaims
blijven voorlopig of onbekend totdat measurement quality betrouwbaar is.

## 35. Data retention and deletion

Definieer vóór pilot:

- raw Matomo retention, aanvankelijk zo kort als methodologisch bruikbaar;
- Thactual daily aggregates conform bestaande metricretentie;
- manifest- en definitionhistorie zolang nodig voor uitlegbaarheid;
- klant/websiteverwijdering in Thactual, Matomo, logs, backups en herstelproeven;
- geen publicatie van een deletion als voltooid voordat alle primaire stores zijn verwerkt.

De bestaande deletion ledger kent alleen Thactual `Client` en `Website`; Sensor/Matomo wordt dus
een expliciete uitbreiding en releasegate.

## 36. Explicit critique of option C

De veronderstelling dat C “het midden” is, is misleidend. C combineert een eigen browserruntime en
publieke ingestion met een analyticsplatform en twee adapters. Het vermijdt de Matomo-client, maar
niet de moeilijkste verantwoordelijkheden rond sessiecontext, consent, delivery, ordering,
deduplicatie, abuse en debugging.

C is strategisch beter wanneer minstens één van deze punten empirisch geldt:

- de begrensde Matomo-client overschrijdt het performancebudget;
- manifest-exposure/processobservaties zijn niet betrouwbaar in Matomo te modelleren;
- centrale PII-rejectie en quotas zijn vóór browseringestion onmisbaar;
- meerdere backendengines moeten op korte termijn worden ondersteund;
- direct Matomo-ingestion is operationeel of juridisch niet beheersbaar.

Daarnaast vervalt optie A wanneer zij niet achter de gestandaardiseerde same-origin Thactual
Gateway kan draaien of per klant handmatige Matomo-inrichting vereist. Eenvoudige installatie en
same-origin levering zijn dus even harde gates als performance en meetbetrouwbaarheid.

Zonder dat bewijs is C meer structurele complexiteit dan productwaarde.

## 37. Recommended architecture

De aanbeveling is **A voor de pilot, ontworpen met een C-compatibele grens**:

- verplichte same-origin Thactual Gateway als stabiel klantcontract;
- eigen observation vocabulary en manifest;
- kleine Thactual-bootstrap rond een gepinde Matomo-client;
- Matomo als raw/processing/archive engine;
- canonical dagelijkse aggregaten in Thactual;
- capabilities in plaats van providerbranches;
- apart trusted outcome endpoint pas wanneer een echte integratie dit nodig heeft;
- expliciete exitcriteria naar C.

Dit is geen keuze voor Matomo als productmodel. Het is een keuze om volwassen trackingmechanica te
lenen terwijl Thactual eerst bewijst welke observations werkelijk besliswaarde hebben.

## 38. Pareto pilot

Pilot met één synthetische site en daarna maximaal twee expliciet gekozen F&F-sites:

1. page/session en active-time bucket;
2. één primary CTA exposure en interaction;
3. één process start en success;
4. één outcome definition met evidence strength;
5. daily URL aggregate en measurement state;
6. één opportunity die Sensor alleen als evidence gebruikt;
7. één effectevaluatie met Sensor coverage;
8. performance-, privacy-, anti-abuse- en deletiontest.

Geen errors, step funnels, devicefriction, internal search, ecommerce of heartbeat in dezelfde
pilotrelease.

## 39. Roadmap placement

Release 13 bestaat uit afzonderlijke gates:

- A — dit architectuurdocument; lokaal afgerond;
- B — capabilitycontract, schema en privacy/threat model; lokaal afgerond;
- C — synthetische Matomo-backed measurement spike; lokaal en op staging geaccepteerd;
- D — observation manifest en één exposure/processfixture; lokaal en op staging geaccepteerd;
- E — Thactual daily aggregates, quality state en intelligencekoppeling; lokaal en op staging
  geaccepteerd;
- F — stagingacceptatie, performance/deletion/abusetests; lokaal en op staging geaccepteerd;
- G — expliciet pilotbesluit; Sensor technisch goedgekeurd, friends-and-family `NO-GO` totdat de
  bestaande harde releasegates zijn afgerond. `thact.nl` is de beoogde eerste interne live
  testwebsite tijdens onboardingontwikkeling.

De bestaande volledige-roadmap- en F&F-gates blijven leidend. Sensor verbreedt niet stilzwijgend de
al geplande onboarding-, privacy- en securityscope.

## 40. Dependencies and affected modules

Waarschijnlijk aangepast in latere implementatiefasen:

- `app/services/analytics_provider.py`;
- `app/services/analytics_journey.py`;
- `app/services/analytics_quality.py`;
- `app/services/effect_analysis.py`;
- `app/services/opportunity_engine.py`;
- `app/services/integration_sync.py`;
- `app/api/routes/integrations.py`;
- `app/models/integrations.py` of nieuwe sensormodellen;
- onboarding, privacy deletion, retention en database roles;
- Compose/deployment pas bij een echte Matomo-pilot.

Mogelijke nieuwe modules:

- `app/models/sensor.py`;
- `app/schemas/sensor.py`;
- `app/services/behavioral_provider.py`;
- `app/services/sensor_manifest.py`;
- `app/services/sensor_quality.py`;
- `app/services/sensor_aggregates.py`;
- `app/api/routes/sensor.py` alleen voor config/status, niet automatisch ingestion;
- `sensor/bootstrap.js`;
- een afzonderlijke adapter voor Matomo Tracking/Reporting.

## 41. Risks

- semantische lock-in ondanks een eigen naamlaag;
- consentverschillen per markt;
- verkeerd gestabiliseerde selectors;
- forged browseroutcomes;
- eventcardinality en opslaggroei;
- dubbele waarheid naast GA4/extern Matomo;
- performanceverslechtering door tracker of manifest;
- onvoldoende deletion propagation;
- opportunityruis door behavioral evidence;
- operationele druk van Matomo/MariaDB op dezelfde VPS.

Mitigatie: één canonical bron per behavioral capability, korte pilot, harde budgets, confidence,
geen automatische issues en expliciete exitcriteria.

## 42. Explicitly not building

Geen analyticsdashboard, attribution, persistent visitorprofiel, cross-device identity, replay,
heatmap, mouse tracking, generic autocapture, tag manager, CDP, full RUM/APM, Sentry- of uptimeclone,
Kafka, Kubernetes of eigen distributed eventplatform.

## 43. Open decisions

1. Welke twee concrete businessprocessen krijgen de eerste outcome definitions?
2. Welke doelmarkten/privacyprofielen gelden voor de twee pilotsites?
3. Is tijdelijke sessieopslag juridisch en methodologisch toegestaan of blijft de pilot volledig
   sessionless/cookieless?
4. Welke raw-retentie is minimaal nodig voor Matomo-archivering en debugging?
5. Blijft de gebatchte canonical eventmapping ook bij langere sessies volledig en geordend?
6. Welke harde performance-uitkomst dwingt overgang van A naar C af?
7. Welke ondersteunde stack krijgt als eerste de automatische Gateway-installatie?
8. Welke serverintegratie kan als eerste trusted outcome leveren?

## 44. Decision

De kernvraag wordt voor de pilot als volgt beantwoord:

> De kleinste betrouwbare observatielaag is voorlopig een streng begrensde Matomo-client en
> EU-Matomo-backend achter een verplichte same-origin Thactual Gateway, eigen vocabulary, manifest
> en aggregate adapter. Optie A blijft alleen geldig wanneer installatie via één ondersteunde
> module automatisch en zonder klantspecifieke Matomo-configuratie verloopt. Bouw de eigen
> ingestion/client van optie C zodra performance, meetbetrouwbaarheid of dit installatiecontract
> aantoonbaar niet wordt gehaald.

Leidend principe: **collect less, observe better, interpret in Thactual**.

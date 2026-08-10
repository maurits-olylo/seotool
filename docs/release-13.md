# Release 13 — Thactual Sensor

Status: fasen A tot en met F lokaal en op staging geaccepteerd. Er is nog geen publieke Gateway-
of Matomo-productiedeployment.

## Fase A — architecture discovery

Status: afgerond.

De architectuur kiest voor een begrensde Matomo-client achter een verplichte same-origin Thactual
Gateway. Eigen vocabulary, manifest en aggregaten voorkomen dat productlogica afhankelijk wordt
van Matomo. Optie C blijft mogelijk achter hetzelfde installatiecontract en wordt gekozen wanneer
performance, meetbetrouwbaarheid of eenvoudige Gateway-installatie aantoonbaar tekortschiet.

Zie `docs/sensor-architecture.md`.

## Fase B — capabilitycontract, schema en privacy-/dreigingsmodel

Status: lokaal geïmplementeerd en getest.

- `BehavioralCapabilities` beschrijft beschikbaar bewijs zonder provider- of eventnamen;
- `BehavioralAggregateProvider` definieert canonical URL-/periodeaggregaten;
- Sensor-manifests staan maximaal twintig expliciete, stabiele locators toe;
- observations hebben één gesloten schema zonder vrije tekst of persoonsgegevens;
- batches bevatten maximaal vijfentwintig observations;
- servertrust is uitsluitend toegestaan voor een serverbevestigde `process_success`;
- onbekende velden, onbekende waarden en ongeldige trustcombinaties worden geweigerd;
- het dreigingsmodel legt browser-, Gateway-, engine- en Thactual-trustgrenzen vast;
- er zijn nog geen publieke routes, secrets, opslagtabellen of deploymentcomponenten toegevoegd.

Lokale acceptatie:

- gerichte Sensor-contracttests: 5 geslaagd;
- volledige regressiesuite: 572 geslaagd;
- Ruff, formattercontrole en diffcontrole: geslaagd;
- geen databasemigratie nodig.

## Volgende fase

## Fase C — synthetische Matomo-backed measurement spike

Status: lokaal geïmplementeerd en op staging geaccepteerd.

- Matomo JavaScript tracker `5.10.0` is als externe proefartifact gepind op versie en SHA-256;
- de externe client wordt nog niet in de repository of productie-image opgenomen;
- de 67.976-byte client is reproduceerbaar gemeten op 22.078 bytes met deterministische gzip;
- de Thactual-bootstrap is na transportoptimalisatie 2.173 bytes onbewerkt en 872 bytes
  gecomprimeerd;
- het gecombineerde resultaat is 22.950 bytes en blijft binnen het budget van 50.000 bytes;
- de bootstrap gebruikt uitsluitend `/thactual/observe`, schakelt cookies en Matomo-
  performancetracking uit en activeert geen generieke content-, link- of DOM-tracking;
- canonical observations worden alleen aan de adapterrand naar Matomo-events of contentacties
  vertaald;
- de synthetische browserproef voert minimaal twintig runs uit en blokkeert bij p75 boven 25 ms,
  meer dan twee trackingrequests of een Sensor-long-task van minimaal 50 ms.

Lokale acceptatie:

- gerichte Sensor-contract-, mapping- en meetscripttests: 10 geslaagd;
- volledige regressiesuite: 577 geslaagd;
- Matomo-checksum en gecomprimeerd bytebudget: geslaagd;
- Ruff, formattering, JavaScript-syntax en diffcontrole: geslaagd;
- lokale Chromiumproef niet uitgevoerd: de Mac heeft geen Playwright-runtime; hiervoor wordt geen
  grote tweede browserinstallatie toegevoegd omdat de bestaande renderworker de gepinde runtime al
  bevat.

Fase C is pas afgerond nadat dezelfde gepinde externe client in de staging-renderworker twintig
keer binnen het browserbudget is gemeten. Een succesvolle spike is geen besluit om Matomo al te
deployen of publieke Gatewayroutes te openen.

Eerste stagingmeting:

- twintig runs, p75 uitvoering 22,5 ms en geen long tasks: geslaagd;
- maximaal vier trackingrequests bij een budget van twee: afgewezen;
- oorzaak in de gepinde Matomo-client: pageviews en gewone events omzeilen de interne bulkqueue;
  contentobservaties gebruiken die queue wel;
- correctie: alle canonical Sensor-observaties lopen via Matomo's publieke `queueRequest`-methode
  als gesloten Sensor-events. Hierdoor blijven bezoek- en URL-context door Matomo verrijkt, terwijl
  de vijf proefobservaties als één bulk-POST kunnen worden verzonden;
- de herhaalmeting rapporteert alleen methode, requestaantal en batchgrootte en logt geen payload.

Tweede stagingmeting:

- omvang 22.950 bytes, p75 uitvoering 24,5 ms, geen long tasks en maximaal één POST: geslaagd;
- de batchteller rapporteerde door een te defensieve Playwright-uitlezing één item, terwijl de
  Matomo-client een JSON-bulkbody verstuurt;
- de acceptatie leest de POST-body nu expliciet als JSON, bewaart alleen het aantal `requests` en
  vereist minimaal vijf items. Een parsefout levert nul op en kan dus niet meer onterecht slagen.

Definitieve stagingacceptatie:

- Matomo-client `5.10.0` en SHA-256 zijn opnieuw geverifieerd;
- twintig Chromium-runs zijn uitgevoerd in de bestaande staging-renderworker;
- p75 uitvoering 16,9 ms bij een budget van 25 ms;
- vijf observations zaten in iedere gemeten bulkbatch;
- maximaal één trackingrequest, uitsluitend via POST;
- geen Sensor-long-task van minimaal 50 ms;
- API en database bleven gezond;
- gereedsignaal: `release-13-phase-c-batch-ok`.

Daarmee is optie A voor deze synthetische scope niet door performance of batching afgewezen. De
volgende fase toetst het observation manifest en één echte exposure-/procesfixture; zij opent nog
geen publieke klantingestion.

## Fase D — observation manifest en exposure-/procesfixture

Status: lokaal geïmplementeerd en op staging geaccepteerd.

- meting start alleen bij expliciete `measurementAllowed: true`;
- manifestversie, exact paginapad en vervaldatum worden vóór koppeling gevalideerd;
- maximaal twintig unieke, allowlisted manifestobservaties zijn toegestaan;
- selectors zijn uitsluitend vaste `data-thactual`-identifiers en nooit vrije CSS-paden;
- ontbrekende of dubbel voorkomende locators worden niet gevolgd;
- maximaal één `IntersectionObserver` meet een exposure pas na minimaal één seconde voor minstens
  de helft in beeld;
- clicks op een expliciet exposure-/interactionelement leveren één interaction;
- een expliciet formulierelement levert `process_start`; alleen een allowlisted proces kan via de
  applicatie-API `process_success` melden;
- herhaald succes, servertrust en vrije evidencewaarden worden niet door de browserruntime
  geaccepteerd;
- `destroy()` ruimt observer, timers en listeners op;
- de fixture verwacht exact de volgorde pageview, exposure, interactie, processtart en processucces
  in één same-origin bulk-POST zonder cookie.

Lokale acceptatie:

- gerichte Sensor-, manifest-, Matomo- en fixturetests: 12 geslaagd;
- volledige regressiesuite: 579 geslaagd;
- actuele bootstrap plus Matomo-client: 24.286 bytes gecomprimeerd van maximaal 50.000 bytes;
- Ruff, formattering, JavaScript-syntax en diffcontrole: geslaagd;
- geen publieke route, secret, databaseopslag of migration toegevoegd.

Staging voert de fase-D-fixture en de twintig performance-runs opnieuw uit, omdat de browserruntime
in deze fase is uitgebreid.

Eerste stagingpoging:

- omvang, p75 uitvoering van 21,0 ms, vijf observations en één POST voldeden;
- één long task in twintig runs blokkeerde de keten vóór de semantische fase-D-fixture;
- de eerste meetversie schreef iedere long task in het volledige venster aan Sensor toe en had geen
  nulmeting, waardoor Chromium- of garbage-collectionruis niet kon worden onderscheiden;
- iedere run krijgt daarom een gekoppelde nulmeting op dezelfde fixture. Een Sensor-long-task is
  alleen toerekenbaar wanneer de Sensorvariant de grens van 50 ms overschrijdt terwijl de nulmeting
  dat niet doet, of meer dan 5 ms boven een eveneens lange nulmeting uitkomt;
- ruwe aantallen en maximale duur voor beide varianten blijven zichtbaar. Het budget blijft nul
  toerekenbare long tasks; alleen de attributiemethode is hersteld.

Definitieve stagingacceptatie:

- twintig gekoppelde nul- en Sensormetingen zijn voltooid;
- p75 Sensoruitvoering 14,6 ms bij een budget van 25 ms;
- nul long tasks in zowel nulmeting als Sensorvariant en dus nul toerekenbare long tasks;
- vijf observations zaten geordend in één same-origin POST;
- de volgorde was `page_view`, `element_exposure`, `element_interaction`, `process_start` en
  `process_success`;
- er zijn geen cookies geplaatst en een dubbele successmelding is geweigerd;
- API en database bleven gezond;
- gereedsignaal: `release-13-phase-d-staging-ok`.

Fase D is hiermee afgerond. De fixture bewijst het manifestcontract en de beperkte browserruntime,
niet een publieke klantinstallatie of productie-ingestion.

## Fase E — dagelijkse aggregaten, meetkwaliteit en intelligence

Status: lokaal geïmplementeerd en op staging geaccepteerd.

- vier additive tabellen leggen manifestversies, outcome-definities, dagelijkse URL-aggregaten en
  periodieke measurement state vast;
- Thactual bewaart uitsluitend dagelijkse URL-aggregaten en geen raw events of visitorprofielen;
- een provider-onafhankelijk contract levert sessies, exposure, interactie, processtart en
  observed/trusted outcomes;
- measurement state wordt alleen `reliable` bij een geldig actief manifest, minimaal zeven
  meetdagen, minimaal 90% paginadekking, maximaal twee dagen freshness-lag, geen rejects en een
  mogelijke outcome/startverhouding;
- een nieuwere slechte quality state blokkeert oudere betrouwbare evidence;
- betrouwbare Sensor-data verrijkt bestaande opportunities als ondersteunend gedragsbewijs, maar
  maakt zelfstandig geen issue of opportunity;
- effectevaluaties nemen Sensor-totalen en coverage mee als `behavior_observation` en blijven
  expliciet `observed_correlation`, nooit een causale claim;
- database-rollen krijgen alleen de benodigde toegang tot de nieuwe tabellen.

Lokale acceptatie:

- gerichte aggregate-, intelligence-, migratie- en fixturetests: 5 geslaagd;
- volledige regressiesuite: 584 geslaagd met één bestaande dependencywaarschuwing;
- Alembic heeft één lineaire head `0061`;
- Ruff, formattering van de gewijzigde Pythonbestanden en diffcontrole: geslaagd;
- geen publieke ingestionroute, site key, Matomo-backend of klantdeployment toegevoegd.

De stagingfixture maakt een synthetische website met 28 meetdagen, bewijst reliable quality,
opportunityverrijking en niet-causale effectevidence, en verwijdert alle synthetische data daarna.

Definitieve stagingacceptatie:

- database is lineair gemigreerd naar `0061`;
- measurement state werd `reliable` met één verwachte en één waargenomen pagina;
- bestaande opportunity-intelligence is met gedragsbewijs verrijkt;
- effectevidence bleef expliciet niet-causaal;
- de fixture heeft alle synthetische gegevens aantoonbaar verwijderd;
- API en database bleven gezond;
- gereedsignaal: `release-13-phase-e-staging-ok`.

Fase E is hiermee afgerond. Fase F toetst de operationele staginggrenzen voor performance,
verwijdering en misbruik; zij opent nog geen friends-and-family-deployment.

## Fase F — performance, privacyverwijdering en gesloten misbruikgrens

Status: lokaal geïmplementeerd en op staging geaccepteerd.

- de bestaande twintig gekoppelde browserruns en het gecomprimeerde clientbudget worden opnieuw
  uitgevoerd tegen exact dezelfde gepinde Matomo-client;
- een batch weigert voortaan ook dubbele event-ID's en begrenst daarmee replay binnen één request;
- persoonsgegevens, onbekende waarden, browsertrust-escalatie en meer dan 25 observations blijven
  contractueel afgewezen;
- website- en klantverwijdering wissen Sensor-aggregaten, manifests, measurement states en
  outcome-definities expliciet voordat de bestaande entiteiten worden verwijderd;
- de deletion ledger bevat alleen type, UUID en tijdstip en blijft idempotent bij herstelherhaling;
- de stagingfixture bewijst dat alle vier Sensor-tabellen leeg zijn en ruimt de synthetische klant
  ook bij een mislukte acceptatie op;
- OpenAPI moet nul publieke Sensor- of observationroutes bevatten.

Deze abuseacceptatie geldt uitsluitend voor de gesloten huidige grens. Rate limits, site/domain-
binding, dagquota, timestampwindow en cross-request replaybescherming blijven harde voorwaarden
voordat in een latere release een publieke Gatewayroute mag worden geopend.

Lokale acceptatie:

- 19 gerichte contract-, privacy-, fixture- en back-up/restoretests geslaagd;
- volledige regressiesuite: 589 geslaagd met alleen de bestaande dependencywaarschuwing;
- alle gewijzigde Pythonbestanden zijn lintvrij en correct geformatteerd;
- Alembic blijft ongewijzigd op één lineaire head `0061`;
- geen migration of extra releaseback-up nodig.

De browseracceptatie downloadt de externe Matomo-client uitsluitend vanuit de gepinde bron, stelt
een harde limiet van 100.000 bytes en verifieert zowel exacte omvang als SHA-256 vóór uitvoering.
De client wordt alleen in een tijdelijk bestand gebruikt en niet in de repository of image
opgenomen.

Eerste stagingpoging:

- omvang, p75-uitvoering van 16,0 ms, vijf observations en één POST voldeden;
- één Sensor-run bevatte een long task van 55 ms tegenover nul in de gekoppelde nulmeting en
  blokkeerde de acceptatie terecht;
- de meetvolgorde bleek iedere nulmeting vóór de Sensorvariant uit te voeren. Daardoor kon
  volgordegebonden browser- of garbage-collectionopbouw systematisch aan Sensor worden
  toegeschreven;
- de paren wisselen daarom deterministisch tussen A/B en B/A. Het rapport toont voor ieder paar
  met een long task het runnummer, de volgorde en beide maximale duren;
- het budget blijft ongewijzigd op nul toerekenbare Sensor-long-tasks.

Definitieve stagingacceptatie:

- de gepinde Matomo-client en totale gecomprimeerde omvang van 24.286 bytes zijn geverifieerd;
- twintig afwisselende A/B–B/A-paren gaven p75 18,4 ms bij een budget van 25 ms;
- er waren nul long tasks in zowel nulmeting als Sensorvariant en dus nul toerekenbare long tasks;
- alle vijf observations werden geordend in één same-origin POST zonder cookies;
- persoonsgegevens, browsertrust-escalatie, een te grote batch en een herhaald event-ID zijn
  afgewezen;
- OpenAPI bevat nul publieke Sensor- of observationroutes;
- manifests, definitions, dagelijkse metrics en measurement states zijn via de deletion ledger
  verwijderd en dezelfde ledgerherhaling was idempotent;
- alle synthetische gegevens zijn verwijderd en API/database bleven gezond;
- gereedsignalen: `release-13-phase-f-browser-ok` en `release-13-phase-f-staging-ok`.

Fase F is hiermee afgerond. Fase G is uitsluitend het expliciete pilotbesluit. Zij opent niet
automatisch een publieke route of friends-and-family-deployment.

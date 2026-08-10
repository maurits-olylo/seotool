# Release 13 — Thactual Sensor

Status: fasen A en B lokaal afgerond; fase C lokaal en op staging geaccepteerd. Er is nog geen
publieke Gateway- of Matomo-productiedeployment.

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

Status: lokaal geïmplementeerd en getest; stagingacceptatie staat open.

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

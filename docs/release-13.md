# Release 13 — Thactual Sensor

Status: fasen A en B lokaal afgerond; nog niet op staging of productie gedeployed.

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

Status: lokaal geïmplementeerd en getest; browsermeting in de bestaande staging-renderworker staat
nog open.

- Matomo JavaScript tracker `5.10.0` is als externe proefartifact gepind op versie en SHA-256;
- de externe client wordt nog niet in de repository of productie-image opgenomen;
- de 67.976-byte client is reproduceerbaar gemeten op 22.078 bytes met deterministische gzip;
- de Thactual-bootstrap is 2.351 bytes onbewerkt en 882 bytes gecomprimeerd;
- het gecombineerde resultaat is 22.960 bytes en blijft binnen het budget van 50.000 bytes;
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

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

Fase C bouwt een synthetische Matomo-backed measurement spike achter het Gateway-contract. Eerst
worden de exacte Matomo-client, scriptomvang, browserkosten en observationmapping reproduceerbaar
gemeten; pas daarna volgt een keuze voor verdere implementatie.

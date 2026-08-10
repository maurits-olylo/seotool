# Release 13 fase B — Sensor privacy- en dreigingsmodel

Status: lokaal contract; nog geen publieke ingestion, Gateway-deployment of Matomo-pilot.

## Scope en trustgrenzen

De browser is onbetrouwbaar. De same-origin Thactual Gateway vereenvoudigt installatie en
browserclassificatie, maar bewijst geen gebruiker, sessie, outcome of tenant. Alleen een
server-side ondertekende integratie kan een `server_confirmed` outcome leveren.

```text
onbetrouwbare browser
  → same-origin Gateway
  → publieke validatie- en begrenzingslaag
  → vervangbare meetengine
  → canonical dagaggregaten in Thactual
```

De pilot verwerkt uitsluitend allowlisted technische observations. DOM-tekst, formulierwaarden,
e-mailadressen, telefoonnummers, user-ID's, IP-adressen en vrije foutteksten zijn verboden.

## Belangrijkste dreigingen en maatregelen

| Dreiging | Gevolg | Verplichte maatregel |
|---|---|---|
| Vervalste browseroutcome | Onterechte effectclaim | browsertrust nooit promoveren; trusted outcome vereist servercredential en replaybescherming |
| Cross-tenant site key | Data bij verkeerde klant | site key binden aan exact geverifieerde origin en tenantscope |
| Replay of duplicaat | Opgeblazen aantallen | uniek event-ID, timestampwindow en idempotente deduplicatie |
| Payload- of cardinaliteitsmisbruik | Kosten/uitval | vaste schema's, batch- en groottelimieten, quota en rate limiting |
| Persoonsdata in waarden/URL | Privacy-inbreuk | geen vrije waarden; queryparameters vóór verzending verwijderen; payloadinhoud niet loggen |
| Manipulatie van manifest | Onbedoelde observatie | ondertekende/gehashte versie, korte geldigheid en alleen stabiele allowlisted locators |
| Supply-chainwijziging | Onbekende clientcode | gepinde lokale assets, reproduceerbare build en hashcontrole |
| Gateway-forwarding misbruik | SSRF of open proxy | vaste upstream, geen clientgestuurde URL en uitgaande netwerkallowlist |
| Verloren of verkeerd geordende events | Onbetrouwbare meting | begrensde batching, event-ID, statusmetrics en quality gate |
| Onvolledige verwijdering | Niet nagekomen privacyclaim | deletion ledger over meetengine, aggregaten, logs, back-ups en hersteltest |

## Dataminimalisatie en levensduur

- standaard cookieless en geen persistent visitor-ID;
- hoogstens een tijdelijke willekeurige session key na afzonderlijk privacybesluit;
- volledige querystrings worden niet verzonden;
- raw meetdata blijft alleen zo kort als archivering en foutonderzoek aantoonbaar vereisen;
- Thactual bewaart canonical dagaggregaten, versies, provenance en kwaliteitsbewijs;
- geen cross-site-identiteit, sessiereplay, heatmap of algemene analyticsprofilering.

## Fase-B-acceptatie

- capabilitygebruik vereist geen providernaam of Matomo-eventnaam;
- manifest en observations weigeren onbekende velden en vrije waarden;
- maximaal twintig manifestobservaties en vijfentwintig events per batch;
- alleen `process_success` met `server_confirmed` mag servertrust krijgen;
- same-origin is installatiebeleid, geen trustbewijs;
- publieke routes, secrets, opslag en migraties worden in deze fase niet toegevoegd.

# Operationeel runbook

## Retentieaudit

Gebruik `python -m app.maintenance retention-audit` in de API-container. Het resultaat is read-only
en toont beleidsversie, datatypes, leeftijdsbuckets, beschermde historie en kandidaten per website.

Controleer vóór uitvoering:

1. recente geverifieerde back-up en herstelbaarheid;
2. stagingproef met dezelfde migratie en beleidsversie;
3. deployment-drain meldt `active=true safe=true`;
4. voldoende vrije opslag en geen actieve onderhoudsoperatie voor dezelfde website.

## Onderbroken retentie

Herhaal een mogelijk onderbroken muterend commando nooit direct. Controleer eerst
`retention_operations`, de actuele audit en de batchtellingen. De scheduler hervat `pending`,
`waiting_for_crawl`, verlopen `running` en `failed` operaties via dezelfde idempotente operatie.

## Vastgelopen worker of operatie

- Controleer containergezondheid, workerregistratie en de maintenancequeue read-only.
- Controleer `status`, `next_attempt_at`, `attempt_count` en `error_message` in PostgreSQL.
- Herstart alleen de geraakte worker; wacht daarna altijd 40 seconden vóór de eerste healthcheck.
- Maak geen tweede operatie voor dezelfde crawlrun en hetzelfde datatype.

## Overvolle queue

- Controleer `/api/v1/system/status`: `warning` betekent dat de waarschuwingsgrens is bereikt;
  `blocked` betekent dat nieuwe taken door admission worden geweigerd.
- Verhoog geen limiet voordat workerstatus, actuele job, NAS-belasting en fouttempo zijn bekeken.
- Crawls blijven als `waiting_for_capacity` in PostgreSQL staan en worden automatisch op
  websiteprioriteit hervat. Start geen duplicaat.
- Integraties worden door de scheduler opnieuw aangeboden. Een interactieve export of verificatie
  mag opnieuw worden gestart nadat capaciteit terug is.

## Dead letters

- Bekijk openstaande records via `GET /api/v1/system/dead-letters`; dit endpoint is uitsluitend
  voor de superuser.
- Controleer queue, taaktype, gekoppelde website, fout en payload. Een dead letter betekent dat
  alle automatische retries zijn uitgeput.
- Gebruik `POST /api/v1/system/dead-letters/<id>/requeue` alleen nadat de oorzaak is verholpen.
  Het product controleert opnieuw de admissiongrens en gekoppelde persistente taak.
- Is opnieuw aanbieden niet zinvol, sluit dan af via
  `POST /api/v1/system/dead-letters/<id>/resolve` met een concrete toelichting.

## Defecte import

- Controleer eerst de blijvende integratiestatus en de afzonderlijke GSC-, GA4- en Bing-fout.
- Controleer daarna de integrationqueue en `integration-worker`; roteer geen token zolang een
  capaciteits- of tijdelijke providerfout nog aannemelijk is.
- Herstel autorisatie alleen via de bestaande OAuth- of tokenroute en start daarna één nieuwe sync.
- Bevestig dat `last_synced_at`, geïmporteerde datumrange en foutstatus weer kloppen.

## Sitemapregressie

- Controleer of robots.txt een sitemap noemt en of de ingestelde of automatisch gevonden root
  bereikbaar is.
- Beoordeel `crawled_urls`, `discovered_urls`, status en resterende sitemapdocumenten. Een
  veiligheidslimiet moet `partially_succeeded` melden en mag nooit stil afkappen.
- De vaste regressieset controleert robots-discovery, ontbreken van een sitemap, 193 documenten en
  begrensde gedeeltelijke verwerking. Een release mag niet door wanneer een van deze tests faalt.

## Schijfruimteprobleem

- Stop nieuwe zware crawls via de deployment-drain en controleer eerst volumes, databasegrootte,
  exports, back-ups en containerlogs read-only.
- Verwijder geen Docker-volume en gebruik geen `VACUUM FULL` als verkennende maatregel.
- Ruim alleen aantoonbaar vervangbare exports of verlopen geverifieerde back-ups op volgens het
  vastgelegde beleid. Databasecleanup loopt uitsluitend via versieerbare retentieoperaties.
- Hervat crawls pas nadat voldoende vrije ruimte, databasehealth en workerhealth zijn bevestigd.

## Deployment, rollback en restore

- Volg voor releases uitsluitend de tweeblokkenroute uit `docs/deployment-synology.md` en houd de
  crawl-drain actief tot migratie, inhoudelijke controle en healthcheck slagen.
- Rollback gebruikt het vorige exacte releasearchief. Draai een downgrade alleen wanneer de
  betreffende migratie aantoonbaar omkeerbaar is en de actuele data daarmee compatibel blijft.
- Restore gebruikt uitsluitend een geverifieerde dump met geldige checksum in een omgeving zonder
  schrijvende API, scheduler of workers. Test herstel eerst geïsoleerd.

## Controle na uitvoering

- Draai de read-only audit opnieuw.
- Vergelijk verwijderde rijen met `rows_deleted` en de voor-/narapporten.
- Controleer dat de laatste volledige crawl, issuebewijs en verificaties nog beschikbaar zijn.
- Controleer API, database, scheduler en geraakte worker vóór het hervatten van crawls.

De exacte deploy-, rollback-, back-up- en herstelcommando's blijven in
`docs/deployment-synology.md` staan.

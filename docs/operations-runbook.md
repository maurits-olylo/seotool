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
- Herstart alleen de geraakte worker; wacht daarna altijd 30 seconden vóór de healthcheck.
- Maak geen tweede operatie voor dezelfde crawlrun en hetzelfde datatype.

## Controle na uitvoering

- Draai de read-only audit opnieuw.
- Vergelijk verwijderde rijen met `rows_deleted` en de voor-/narapporten.
- Controleer dat de laatste volledige crawl, issuebewijs en verificaties nog beschikbaar zijn.
- Controleer API, database, scheduler en geraakte worker vóór het hervatten van crawls.

De algemene deploy-, rollback-, back-up- en herstelprocedures blijven in
`docs/deployment-synology.md` staan. Queueoverloop, defecte imports en schijfruimtebewaking worden
in Release 2 verder uitgewerkt.

# Release 6 — lokale releasecandidate

Status: lokaal afgerond; staging en productie nog niet uitgevoerd.

## Scope

- Zelfstandig taakcentrum met zoeken en filters voor status, prioriteit, vakgebied, eigenaar en
  verificatiestatus.
- Persistente taakmeldingen met per gebruiker een eigen gelezen-status voor status-, eigenaar- en
  verificatiewijzigingen.
- Uitgebreide taakrollen voor contentredactie, UX/UI, webdevelopment, SEO, analytics en
  websitebeheer, met behoud van bestaande rollen.
- URL-dekkingsbeeld met actuele en historische ontdekbronnen, bronoverlap en expliciete
  betrouwbaarheid op basis van de laatste volledige crawl.
- Gerichte CSV-export van de zichtbare takenwerkvoorraad en uitgebreidere URL- en Excel-exports.

## Veilige standaardinstellingen

- `PAGESPEED_ENABLED=false` blijft ongewijzigd.
- `RENDERING_ENABLED=false` blijft ongewijzigd; Release 6 activeert JavaScript-rendering niet.
- Meldingen zijn klant- en websitegebonden; gelezen-status wordt afzonderlijk per gebruiker
  opgeslagen.
- De bestaande begrensde exportqueue blijft in gebruik.
- De niet-operationele Linux-worker maakt geen deel uit van deze release.

## Deploymentimpact

- Migration `0042` voegt alleen `task_notifications` en `task_notification_receipts` met indexes
  toe en verruimt de toegestane taakrollen. Er worden geen bestaande rijen verwijderd of
  herschreven.
- API, gewone worker, crawlworkers, integration-worker en exportworker bevatten gedeelde geraakte
  code. De schedulerlogica is niet gewijzigd.
- Een extra releaseback-up is voor deze additieve, transactionele migration niet vereist. De
  bestaande geverifieerde herstelroute blijft wel een deploymentvoorwaarde.

## Lokale acceptatie

- Ruff: geslaagd.
- Volledige testsuite: 409 tests geslaagd; alleen de bestaande Starlette/httpx-waarschuwing.
- JavaScript-syntax en diff-controle: geslaagd.
- Alembic: één head op `0042`, lineair vanaf `0041`.
- Development-, productie- en staging-Compose-configuratie: geldig.

# Release 5 — lokale releasecandidate

Status: lokaal geïmplementeerd, integraal getest en op 4 augustus 2026 succesvol naar staging
uitgerold. Nog niet op productie gedeployed.

## Scope

- Begrensde PageSpeed Insights-integratie voor maximaal tien risicogestuurde, template-diverse
  URL's per batch.
- Genormaliseerde opslag van Lighthouse-labdata, CrUX-velddata en compact auditbewijs via
  migration `0041`.
- Uitlegbare performance-issues op concrete mislukte audits; categoriescores alleen zijn geen
  issue.
- Contextuele structured-data-validatie voor Product, Article, Organization, LocalBusiness,
  Event en VideoObject.
- Sitemap- en robotskwaliteit voor ontbrekende, dubbele, ongeldige en websitevreemde
  URL-informatie.

## Veilige standaardinstellingen

- `PAGESPEED_ENABLED=false`; activering vereist daarnaast `PAGESPEED_API_KEY`.
- `RENDERING_ENABLED=false`; Release 5 activeert JavaScript-rendering niet.
- De performancequeue is begrensd op drie actieve en tien wachtende taken met een timeout van
  twintig minuten.
- De niet-operationele Linux-worker maakt geen deel uit van deze release.

## Deploymentimpact

- Migration `0041` maakt alleen de nieuwe tabel `performance_observations` en indexes aan. Er
  worden geen bestaande rijen gewijzigd of verwijderd.
- API, integration-worker, gewone worker en crawlworkers bevatten geraakte code. De scheduler
  gebruikt de nieuwe queuepolicyversie.
- Een extra releaseback-up is voor deze additieve migration niet vereist; de bestaande
  geverifieerde herstelroute blijft wel een deploymentvoorwaarde.

## Lokale acceptatie

- Ruff: geslaagd.
- Volledige testsuite: 404 tests geslaagd; alleen de bestaande Starlette/httpx-waarschuwing.
- Alembic: één head op `0041`, lineair vanaf `0040`.
- Development-, productie- en staging-Compose-configuratie: geldig.
- Staging: migration `0041`, gezonde API en database, aanwezige tabel
  `performance_observations`, `PAGESPEED_ENABLED=false` en `RENDERING_ENABLED=false` bevestigd.
- Productieacceptatie volgt afzonderlijk via de terminal-first releaseprocedure.

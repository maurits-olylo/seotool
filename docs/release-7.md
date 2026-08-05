# Release 7 — Matomo en analytics-meetkwaliteit

Status: afgerond en op 5 augustus 2026 succesvol naar staging en productie uitgerold. Staging
gebruikte releasecommit `c3bd183`; productie gebruikte het definitieve documentatiearchief uit
commit `705640a` met dezelfde applicatiecode.

## Scope

- Veilige Matomo-verbinding via HTTPS en POST, met versleutelde tokenopslag en expliciete
  selectie van één Matomo-site.
- Afzonderlijke opslag van geaggregeerde Matomo-pagina-, verkeersbron-, doel- en conversiedata.
- Koppeling van Matomo-pagina's aan het blijvende URL-register, inclusief matchpercentage en
  begrensde lijst met ongekoppelde URL-varianten.
- Expliciete dekkingsstatus voor transities, downloads, outbound links en interne zoekopdrachten.
- Provider-onafhankelijke analyticslaag voor issue-impact en klantrapportages.
- Eén expliciet gekozen primaire analyticsbron per website. GA4 en Matomo worden nooit
  stilzwijgend gecombineerd of als elkaars terugval gebruikt.
- Beheerinterface voor Matomo-verbinding, siteselectie, synchronisatie en primaire-bronkeuze,
  met herkenbare providericonen en vernieuwde Bing-backlinkupload.

De eerste beoogde website voor de koppeling is `human.nl`. Het serveradres, API-token en de
Matomo-site-ID zijn operationele secrets of configuratiewaarden en staan niet in Git.

## Privacy en veilige standaarden

- Alleen HTTPS Matomo-servers met publiek bereikbare adressen worden geaccepteerd.
- Het token staat uitsluitend in de POST-body, wordt versleuteld opgeslagen en verschijnt niet in
  URLs, API-responses of logs.
- Redirects van de Matomo API worden geweigerd.
- Alleen geaggregeerde rapportdata wordt geïmporteerd; geen raw visits, bezoekers-IP's,
  bezoekersprofielen of user-ID's.
- Interne zoekopdrachten worden niet geïmporteerd.
- Functionele URL-queryparameters blijven behouden; de bestaande normalisatie verwijdert alleen
  bekende trackingparameters en websitegebonden expliciet genegeerde parameters.
- `PAGESPEED_ENABLED=false` en `RENDERING_ENABLED=false` blijven ongewijzigd.
- De niet-operationele Linux-worker maakt geen deel uit van deze release.

## Database en deploymentimpact

- Migration `0043` voegt een generiek JSON-instellingenveld toe aan integratieverbindingen.
- Migration `0044` voegt afzonderlijke tabellen voor geaggregeerde Matomo-metrics toe.
- Migration `0045` voegt de expliciete primaire analyticsbron aan website-instellingen toe.
- Alle wijzigingen zijn additief en verwijderen of herschrijven geen bestaande rijen. Een extra
  releaseback-up is daarom niet vereist; de bestaande geverifieerde herstelroute blijft een
  deploymentvoorwaarde.
- Geraakte services: API, integration-worker en scheduler. Andere workers hoeven niet te worden
  herbouwd of herstart.

## Lokale acceptatie

- Ruff: geslaagd.
- Volledige testsuite: geslaagd; alleen de bestaande Starlette/httpx-waarschuwing.
- Alembic: één lineaire head op `0045` vanaf `0042`.
- Diffcontrole: geslaagd.
- Staging: migration `0045`, gezonde API en database, aanwezige Matomo-tabellen en nieuwe
  integratiekolommen, `PAGESPEED_ENABLED=false` en `RENDERING_ENABLED=false` bevestigd.
- Productie: migration `0045`, gezonde API, database, integration-worker en scheduler, aanwezige
  Matomo-tabellen en integratiekolommen en beschikbare Matomo- en primaire-bronroutes bevestigd.
  PageSpeed en JavaScript-rendering blijven uitgeschakeld. De veilige crawl-drain is opgeheven met
  nul actieve of wachtende taken.

# Meest gelinkte pagina’s

Het scherm **Metingen → URL’s** bevat een top 10, een doorzoekbare en sorteerbare tabel en per doelpagina de verwijzende pagina’s met hun linkteksten.

## Definitie

- Bron: de laatst afgeronde, geslaagde `full_site_crawl` van de geselecteerde website. Light checks en mislukte crawls vervangen deze gegevens niet.
- Elke bronpagina telt eenmaal per doelpagina. Meerdere links of linkteksten vanaf dezelfde bron verhogen de telling niet.
- Interne nofollow-links tellen mee; links naar dezelfde pagina en links buiten de website tellen niet mee.
- Geen samenvoeging op redirect of canonical: de geregistreerde linkbestemming bepaalt de telling.
- De tabel omvat gemeten URL’s en geregistreerde interne linkdoelen uit deze crawl, ook bij nul inkomende links. Niet-gemeten doelen krijgen geen verzonnen HTTP-status.
- Verschil vergelijkt met de voorgaande geslaagde volledige crawl. Geen eerdere meting voor een URL geeft `—`, geen nul.
- De meetdatum en status komen uit dezelfde volledige crawl; een nieuwere light check wijzigt deze historische status niet.
- Linkdetails ouder dan de bewaartermijn (momenteel 180 dagen) worden conservatief niet gebruikt, ook wanneer een beschermde crawl mogelijk nog detail bevat. Zonder bruikbare recente crawl vraagt de interface om een volledige crawl.
- Dit zijn eigen crawlgegevens, geen GSC-tellingen. Crawlbereik en instellingen bepalen de dekking.

## API

Bestaande API-authenticatie en websiteautorisatie blijven van toepassing.

- `GET /api/v1/websites/{website_id}/internal-links`: `q`, `order` (`links_desc`, `links_asc`, `url`), `offset`, `limit` (1–100, standaard 25). De top 10 blijft websitebreed bij zoeken in de tabel.
- `GET /api/v1/websites/{website_id}/internal-links/{url_id}/sources`: verplichte `crawl_run_id`, `offset`, `limit`. Bronpagina’s worden uniek gepagineerd, met hun unieke linkteksten uit dezelfde crawl.

De telling wordt in de database geaggregeerd. De API sorteert en filtert de doelpagina’s; individuele linkrecords worden alleen voor de opgevraagde bronpagina’s geladen.

## Gewijzigde bestanden

Nieuw:
- `app/services/internal_links.py`
- `app/api/routes/internal_links.py`
- `app/ui/internal-links.js`
- `app/ui/internal-links.css`
- `tests/test_internal_links.py`
- `docs/internal-link-overview.md`

Gewijzigd:
- `app/main.py`: route registreren.
- `app/ui/index.html`: overzicht en bijbehorende bestanden laden.
- `app/ui/app.js`: overzicht laden bij URL-weergave.
- `tests/test_api.py`: actuele versie van het interfacebestand controleren.

## Verificatie en uitrol

76 gerichte API- en exporttests geslaagd (inclusief vijf tests voor dit overzicht). Browsercontrole met afzonderlijke testgegevens: grafiek, bronpagina’s, HTML-escaping, websitewissel en weergave op desktop en mobiel. De voorbeelden zijn geen actuele productiemetingen.

Geen nieuwe dependency, migratie of workerwijziging. Voor productie hoeft alleen de API-service met de meegeleverde interface opnieuw gebouwd en gestart te worden, via de bestaande Synology-deploymentroute. Deze fase levert de lokaal geteste wijziging; productie-uitrol volgt apart.

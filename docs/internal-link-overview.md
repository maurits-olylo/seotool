# Interne links: aandachtspunten

Het scherm **Metingen → URL’s** toont compacte selecties voor weinig verwijzingen, verloren verwijzingen, gelinkte foutpagina’s, breed herhaalde links en technische URL’s. De tabel toont vijf rijen per pagina. Bronpagina’s en linkteksten openen op aanvraag; tabellen hebben een begrensde hoogte.

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


## Verbetering 12 september 2026

De grote top-10-grafiek is uit de interface verwijderd. De API behoudt `top` voor compatibiliteit. De interface selecteert standaard `view=attention&order=priority&limit=5`.

- `low`: status 200, maximaal twee unieke verwijzende pagina’s, geen herkend technisch pad. Dit is een controlepunt, geen bewijs van een orphan page of SEO-fout.
- `lost`: een negatieve verandering tegenover de vorige volledige crawl; een verschil kan ook door gewijzigd crawlbereik ontstaan.
- `errors`: status 400 of hoger met minstens één verwijzende pagina. Deze komen eerst, gesorteerd op aantal verwijzingen; daarna verliezen en weinig gelinkte pagina’s.
- `repeated`: aantal verwijzende pagina’s is minstens 80% van het aantal URL’s met snapshots in deze crawl, bij minstens tien gemeten URL’s. Dit is een frequentiesignaal; menu-, footer- of hoofdtekstpositie is onbekend.
- `technical`: exacte paden en onderliggende paden van `/admin-panel`, `/wp-admin`, `/wp-json`, `/cdn-cgi`, `/api`, plus `/wp-login.php`. Case en URL-encoding worden genormaliseerd. Dit is een beperkte herkenningslijst, geen volledige paginatypeclassificatie.
- `pages` sluit uitsluitend herkende technische URL’s uit; `all` behoudt alles. Technische foutpagina’s en verliezen blijven in aandachtspunten zichtbaar.

API-filter `view` ondersteunt deze waarden plus `attention`. `summary` bevat websitebrede aantallen vóór zoeken en paginering; categorieën kunnen overlappen. Er worden geen links verwijderd of opnieuw geclassificeerd in de database.

Zeven gerichte tests geslaagd. Browsercontrole gebruikt synthetische gegevens en controleert vijf rijen, filters, bronpagina’s, escaping, paginering, mobiel en websitewissel. Geen migratie vereist. Alleen API/interface moet bij een volgende uitrol worden herbouwd.

Ook gewijzigd: `scripts/verify-internal-links-release.py` controleert het nieuwe interfacekenmerk. Deze controle leest de dataservice onder de API-databaserol en publieke assets; productie-HTTP met gebruikerssessie wordt afzonderlijk in de ingelogde interface gecontroleerd.


## Deelresultaten uit volledige crawls — 14 september 2026

Afgeronde `partially_succeeded` volledige crawls zijn nu ook beschikbaar in het linkoverzicht en de bronpagina’s. De laatste twee afgeronde volledige crawls worden geselecteerd op einddatum. Lopende, gepauzeerde, geannuleerde en mislukte crawls blijven uitgesloten, evenals light checks. De oorspronkelijke status wordt niet gewijzigd.

Het overzicht vermeldt bij deelresultaten aantallen verwerkte en mislukte URL’s en waarschuwt dat linkaantallen onvolledig kunnen zijn. Als een van beide vergelijkingscrawls deels geslaagd is, wordt geen verschil berekend; daardoor worden ontbrekende bronnen niet als verloren verwijzingen gepresenteerd. Bestaande frequentie- en laag-aantalfilters zijn controlepunten op de beschikbare gegevens.

De URL-dekkingsmelding benoemt een deels geslaagde crawl als afgerond met ontbrekende resultaten, in plaats van te melden dat geen volledige crawl bestaat. Dekking en kortste route blijven voorlopig (`reliable=false`); beschikbare routes kunnen wel worden getoond.

Aanvullend gewijzigd: `app/api/routes/discovery.py` voor dekkingscontext en beschikbare routes. Geen migratie en geen nieuwe crawl vereist om bestaande deelresultaten te tonen.

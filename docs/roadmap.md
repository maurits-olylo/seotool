# Roadmap

Dit document is de actuele uitvoeringsplanning. `AGENTS.md` beschrijft de vaste werkwijze en
productvisie; `docs/architecture.md` beschrijft de technische werking. Een fase is pas afgerond
nadat de code is getest, gedeployed en het productieresultaat is gecontroleerd.

## Huidige status

- Actieve ontwikkellijn: fase 4 — resterende SEO-functionaliteit.
- Productie: `https://seo.thact.nl` op Synology NAS `192.168.2.20`.
- Laatste afgeronde kwaliteitscontrole: 124 tests, Ruff en JavaScript-syntax geslaagd.
- Open productiecontrole fase 1: bevestigen dat `jobsatpearle.be` na de lopende crawl niet meer als
  actieve URL van `werkenbijgrandvision.nl` verschijnt.

## Fase 1 — Multi-client domeinisolatie

Status: technisch geïmplementeerd en gedeployed; productievalidatie loopt.

- Basis-host, equivalente www/root-variant en expliciete subdomeinen vormen de website-scope.
- Sitemapimport, interne links, handmatige registratie en bestaande URL-records respecteren scope.
- Eerder vervuilde records worden vóór ieder crawltype gedeactiveerd.
- Standaard URL-overzichten tonen alleen actieve URL's; historische records blijven bewaard.
- Geen klantspecifieke domeinuitzonderingen.

Acceptatie:

- `jobsatpearle.be` verschijnt nergens als actief resultaat van `werkenbijgrandvision.nl`.
- Een toekomstige zelfstandige website voor `jobsatpearle.be` blijft mogelijk.
- Data van andere klanten blijft intact.

## Fase 2 — Onboarding en Organisatie-UI

Status: afgerond en gedeployed.

- Klant en eerste website atomair aanmaken.
- Website-instellingen onderdeel maken van onboarding.
- Duidelijke laad-, succes- en foutstatussen; dubbel verzenden voorkomen.
- Na bevestiging een eerste volledige crawl veilig inplannen.
- Zoeken, openen, hernoemen en verwijderen behouden.
- Klant- en websitelocatie na refresh herstellen.
- Rollen en klanttoegang via de API blijven afdwingbaar.

## Fase 3 — Tweede-klantvalidatie

Status: in uitvoering.

Gebruik `werkenbijgrandvision.nl` als praktijktest voor onboarding, crawl, issues, vacatures,
integraties, exports, rapportage en rollen. Los uitsluitend reproduceerbare multi-clientproblemen op.

Validatie omvat zowel productiecontroles als geautomatiseerde regressietests die aantonen dat een
gebruiker geen websites, URL's, crawls, issues of rapportages van een andere klant kan benaderen.

## Fase 4 — Resterende SEO-functionaliteit

Status: in uitvoering.

- Thin-contentdetectie en ruisarme wijzigingsdetectie aanscherpen.
- Verouderde content buiten vacatures toevoegen met voorzichtige signalering.
- GSC/GA4-impact en consultantinzichten verder prioriteren.
- Ontbrekende technische controles uit de acceptatielijst valideren.
- Inzichten alleen bij voldoende bewijs als harde issues behandelen.

## Fase 5 — Bing hervatten

Status: gepauzeerd totdat voldoende Bing Webmaster Tools-data beschikbaar is.

- Bing aanvullend vergelijken met Google en databron expliciet tonen.
- Backlinkdiscovery en veranderingen toevoegen wanneer de officiële API dit ondersteunt.
- Geen scraping-workaround voor ontbrekende officiële functionaliteit.

## Fase 6 — Productieafronding

Status: gepland.

- Volledige acceptatiecontrole met minimaal twee klanten.
- Scheduler, workers, exports, back-up, restore, updates en rollback valideren.
- Logging, operationele status en documentatie afronden.
- Reproduceerbare NAS-installatie en alle relevante MVP-acceptatiecriteria controleren.

## Deploymentafspraak

Releases worden als Git-archive naar `/tmp/seotool-<commit>-r<nummer>.tar.gz` geschreven. Upload naar
de NAS gebeurt via SSH-streaming met `dd`. Controleer op de NAS altijd eerst SHA-256, pak daarna uit
met `sudo tar --no-same-owner` en bouw en herstart alleen geraakte services. Migrations worden alleen
uitgevoerd wanneer een nieuw Alembic-bestand onderdeel van de release is.

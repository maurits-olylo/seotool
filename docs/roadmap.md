# Roadmap

Dit document is de actuele uitvoeringsplanning. `AGENTS.md` beschrijft de vaste werkwijze en
productvisie; `docs/architecture.md` beschrijft de technische werking. Een fase is pas afgerond
nadat de code is getest, gedeployed en het productieresultaat is gecontroleerd.

## Huidige status

- Actieve ontwikkellijn: fase 4 — resterende SEO-functionaliteit.
- Eerstvolgend ontwikkelitem na release `da68459`: Bing Webmaster Tools hervatten.
- Productie: `https://seo.thact.nl` op Synology NAS `192.168.2.20`.
- Laatste afgeronde kwaliteitscontrole: 154 tests en Ruff geslaagd.
- Open productiecontrole fase 1: bevestigen dat `jobsatpearle.be` na de lopende crawl niet meer als
  actieve URL van `werkenbijgrandvision.nl` verschijnt.

## Operationele veiligheid — globale deployment-drain

Status: geïmplementeerd, gedeployed en met een actieve crawl gevalideerd.

- Nieuwe handmatige crawls, onboarding-crawls en scheduler-crawls worden centraal geblokkeerd.
- Actieve crawls ronden de huidige URL af en gaan daarna naar `paused`.
- De toestand en de door deployment gepauzeerde job-ID's blijven in PostgreSQL bewaard.
- Hervatten start alleen crawls die door de actuele deployment zijn gepauzeerd.
- Een timeout of mislukte deployment laat de blokkade actief totdat expliciet wordt hervat.

Acceptatie:

- `pause-crawls --wait` meldt pas `safe=true` wanneer geen crawl meer verwerkt.
- Een startverzoek tijdens de drain krijgt HTTP 503 en de scheduler maakt geen crawljob aan.
- Na healthchecks hervat `resume-crawls` alleen deployment-gepauzeerde crawls.

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

### Visuele vernieuwing publieke website

Status: afgerond, gedeployed en geaccepteerd.

- Bestaande kleuren en typografie behouden.
- Ruimere hero en productvisual toevoegen vóór de login.
- Sticky uitleg links koppelen aan scrollende productbeelden rechts.
- Prioriteiten, veranderingen, sitestructuur en actiebeheer uitleggen.
- Het ingelogde dashboard functioneel en compact houden.

### Contextuele JobPosting-identifiers

Status: technisch geïmplementeerd; deployment en productievalidatie volgen.

- Ontbrekende aanbevolen velden niet zelfstandig als waarschuwing tonen.
- Vacatures zonder identifier sitebreed op sterke inhoudelijke gelijkenis vergelijken.
- Alleen bij aantoonbaar verwarringsrisico een contextueel issue maken.
- Groepsgrootte, overlap en gerelateerde URL's als technisch bewijs tonen.
- Vanaf vijf vergelijkbare vacatures de prioriteit van laag naar middel verhogen.

- Thin-contentdetectie en ruisarme wijzigingsdetectie aanscherpen.
- Verouderde content buiten vacatures toevoegen met voorzichtige signalering.
- GSC/GA4-impact en consultantinzichten verder prioriteren.
- Ontbrekende technische controles uit de acceptatielijst valideren.
- Inzichten alleen bij voldoende bewijs als harde issues behandelen.

### Gerichte pagina-exports

Status: geïmplementeerd en gedeployed; productievalidatie met een gefilterde export blijft open.

- Voeg bovenaan `URL's`, `Wijzigingen` en `Vacatures` een eigen exportknop toe.
- Exporteer per knop uitsluitend het datatype en de kolommen van de betreffende pagina.
- Pas de actieve zoekopdracht, filters en geselecteerde website toe op de export.
- Ondersteun zo herbruikbare lijsten rond een specifiek onderwerp of interessegebied zonder het
  volledige algemene workbook te hoeven downloaden.
- Vermeld website, exportmoment en toegepaste filters in iedere export.

Acceptatie:

- Een gefilterd URL-overzicht levert alleen de zichtbare URL-selectie als exportdataset op.
- Een gefilterd wijzigingenoverzicht levert alleen de bijbehorende wijzigingen op.
- Een gefilterd vacatureoverzicht levert alleen de geselecteerde vacatures en hun relevante status
  en bevindingen op.

### Waarde en betrouwbaarheid van het URL-overzicht

Status: technisch geïmplementeerd; lege-paginadetectie, context voor onvolledige crawldiepte en de
concrete kortste interne linkroute zijn beschikbaar. Productievalidatie volgt.

- Onderzoek welke bruikbare signalen in het URL-overzicht ontbreken en welke bestaande waarden
  onvoldoende betrouwbaar of onvoldoende verklaard zijn.
- Signaleer indexeerbare 200-pagina's die vrijwel leeg zijn en alleen basismetadata zoals title en
  H1 bevatten met een controlegerichte vraag: “Klopt het dat deze pagina live staat?”
- Maak onderscheid tussen een bewust korte functionele pagina, een lege template, soft 404 en een
  inhoudelijk dunne landingspagina.
- Verklaar waarom crawldiepte onbekend is, bijvoorbeeld niet intern bereikbaar, alleen via sitemap
  gevonden, crawl afgebroken of buiten de voltooide crawlgrens.
- Valideer crawldiepte tegen de werkelijk kortste interne linkroute en voorkom dat een oudere of
  onvolledige crawl een misleidende waarde toont.
- Voeg context en aanbevolen vervolgactie toe in plaats van alleen URL, status en diepte te tonen.

Praktijktests:

- `https://www.schipperkozijnen.nl/aluminium-achterdeuren`: lege live pagina herkennen en gericht
  laten beoordelen.
- `https://www.schipperkozijnen.nl/comfort`: onderzoeken waarom crawldiepte 2 wordt getoond en de
  kortste interne route aantoonbaar maken.

### Ruisarme en verklaarbare wijzigingen

Status: in uitvoering; vergelijkingsdata, relevantieniveau, mogelijke impact en aanbevolen controle
zijn technisch toegevoegd. Verdere normalisatie van dynamische templatewaarden volgt.

- Inventariseer welke kleine technische of cosmetische verschillen nu onterecht een wijziging
  triggeren.
- Normaliseer dynamische, niet-inhoudelijke waarden waar dit veilig en reproduceerbaar kan.
- Maak onderscheid tussen kleine technische wijziging, inhoudelijke wijziging en SEO-kritieke
  wijziging.
- Toon altijd de vorige en huidige meetdatum: “gewijzigd ten opzichte van”.
- Toon wat inhoudelijk veranderde, waarom dit mogelijk relevant is en welke controle wordt
  aanbevolen.
- Groepeer samenhangende wijzigingen per URL en crawl in één gebeurtenis.
- Geef kleine wijzigingen minder nadruk of verberg ze standaard, zonder de onderliggende historie
  te verwijderen.

Acceptatie:

- Een gebruiker kan direct zien tussen welke twee snapshots is vergeleken.
- Iedere zichtbare wijziging bevat betekenis, mogelijke impact en een praktisch controledoel.
- Witruimte, volgorde zonder semantische betekenis en bekende dynamische templatewaarden leveren
  geen prominente wijzigingsmelding op.

## Fase 5 — Bing hervatten

Status: gepauzeerd totdat voldoende Bing Webmaster Tools-data beschikbaar is.

- Bing aanvullend vergelijken met Google en databron expliciet tonen.
- Backlinkdiscovery en veranderingen toevoegen wanneer de officiële API dit ondersteunt.
- Geen scraping-workaround voor ontbrekende officiële functionaliteit.

## Fase 6 — Productieafronding

Status: gepland.

- Volledige acceptatiecontrole met minimaal twee klanten.
- Scheduler, workers, exports, back-up, restore, updates en rollback valideren.
- Pauzeren, hervatten, stoppen en herstel na worker-restart operationeel valideren.
- Globale deployment-drain bouwen:
  - nieuwe crawls en schedulerjobs tijdelijk blokkeren;
  - alle actieve crawls na de huidige URL veilig pauzeren;
  - alleen crawls met pauzereden `deployment` registreren voor hervatting;
  - wachten totdat geen crawl meer actief verwerkt wordt;
  - na deployment eerst healthchecks uitvoeren;
  - deployment-crawls daarna expliciet en automatisch hervatten;
  - bij een mislukte deployment crawls veilig gepauzeerd laten.
- Logging, operationele status en documentatie afronden.
- Reproduceerbare NAS-installatie en alle relevante MVP-acceptatiecriteria controleren.

## Fase 7 — Schaalbaarheid en parallelle crawls

Status: later; pas oppakken wanneer het aantal gelijktijdige klanten de enkele crawl-worker
structureel laat vollopen.

- Laat volledige sitecrawls van verschillende websites gecontroleerd parallel draaien.
- Behoud maximaal één actieve crawl per website en voorkom dubbele verwerking van dezelfde job.
- Maak een globale limiet voor gelijktijdige crawls instelbaar, met een veilige NAS-standaard.
- Verdeel capaciteit eerlijk over klanten zodat één grote website de wachtrij niet langdurig blokkeert.
- Begrens totale databaseverbindingen, geheugen, CPU en uitgaand verkeer.
- Toon per job duidelijk `in wachtrij`, wachtrijpositie en beschikbare worker-capaciteit.
- Laat de globale deployment-drain alle parallelle workers veilig pauzeren en gericht hervatten.

Acceptatie:

- Twee volledige sitecrawls van verschillende klanten kunnen gelijktijdig voortgang boeken.
- Een tweede crawl voor dezelfde website blijft geblokkeerd.
- De ingestelde globale capaciteitslimiet wordt nooit overschreden.
- Pauzeren, deployen en hervatten werkt aantoonbaar voor meerdere actieve crawls tegelijk.

## Fase 8 — Matomo-integratie

Status: later; uitsluitend oppakken nadat de Bing Webmaster Tools-integratie is hervat en
gevalideerd.

- Een Matomo-site koppelen via server-URL, `idSite` en een API-token met leestoegang.
- API-tokens versleuteld bewaren en uitsluitend via POST versturen, nooit in URL's of logs.
- Bezoeken, paginaweergaven, landingspagina's, verkeersbronnen, doelen en conversies importeren.
- Matomo-pagina's via genormaliseerde URL's aan het blijvende URL-register koppelen.
- Issues en wijzigingen verrijken met verkeers- en conversie-impact, gelijkwaardig aan GA4-data.
- Matomo naast GA4 ondersteunen; geen van beide integraties verplicht maken.

Acceptatie:

- Een gebruiker kan een Matomo-verbinding testen en vervolgens de juiste site selecteren.
- Alleen gegevens van de gekoppelde Matomo-site worden opgeslagen en getoond.
- Verkeers- en conversiedata zijn per URL en vergelijkingsperiode beschikbaar.
- Een ongeldig of ingetrokken token veroorzaakt een duidelijke fout zonder geheimen te loggen.

## Deploymentafspraak

Releases worden als Git-archive naar `/tmp/seotool-<commit>-r<nummer>.tar.gz` geschreven. Upload naar
de NAS gebeurt via SSH-streaming met `dd`. Controleer op de NAS altijd eerst SHA-256, pak daarna uit
met `sudo tar --no-same-owner` en bouw en herstart alleen geraakte services. Migrations worden alleen
uitgevoerd wanneer een nieuw Alembic-bestand onderdeel van de release is.

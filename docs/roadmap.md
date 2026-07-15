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

### Betrouwbare sitemapjobs

Status: technisch geïmplementeerd; deployment en productievalidatie volgen.

- Ingestelde sitemaps aanvullen met sitemapverwijzingen uit `robots.txt`.
- Zonder verwijzing gecontroleerd `/sitemap.xml` proberen.
- Automatisch gevonden sitemapadressen voor volgende jobs bewaren.
- Unieke gevonden URL's en gelezen sitemapdocumenten tellen.
- Een job zonder beschikbare sitemap niet langer leeg als geslaagd tonen.

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

Status: in uitvoering; OAuth-koppeling is hersteld en HUMAN is gekoppeld. Data-import volgt.

- Bing aanvullend vergelijken met Google en databron expliciet tonen.
- Backlinkdiscovery en veranderingen toevoegen wanneer de officiële API dit ondersteunt.
- Geen scraping-workaround voor ontbrekende officiële functionaliteit.

## Fase 6 — Intelligente diagnose en UX/UI-polish

Status: gepland; direct na de eerste werkende Bing-data-import oppakken als kernfase van het
product.

### Van signaal naar diagnose

- Losse URL-signalen clusteren tot één waarschijnlijk onderliggend probleem.
- URL-patronen herkennen, waaronder paginering, filters, facetten, parameters, templates en
  canonical- of redirectconfiguraties.
- Vergelijkbare paginagroepen vormen en afwijkingen binnen zo'n groep aanwijzen in plaats van alle
  normale waarden als losse regels te tonen.
- Crawldiepte, indexatie, interne links, wijzigingen, schema en verkeersdata gezamenlijk beoordelen.
- Mogelijke hoofdoorzaak, alternatieve verklaring, vertrouwen en technisch bewijs apart tonen.
- Eén hoofdissue koppelen aan geraakte URL's en onderliggende signalen zonder historie te verliezen.
- Interne-linkproblemen ook vanuit de bronpagina groeperen: één pagina met meerdere dode uitgaande
  links wordt één diagnose met de afzonderlijke doelen als bewijs, niet meerdere losse hoofdissues.
- Per defecte link doel-URL, ankertekst, status/fout, eerste waarneming en aanbevolen vervanging of
  verwijdering tonen.
- Zowel bronpatronen als doelpatronen ondersteunen: meerdere defecte links op één pagina en één
  defect doel waar veel pagina's naartoe linken zijn verschillende, maar gerelateerde diagnoses.

### Van diagnose naar exact handelingsadvies

- Uitleggen waarom het probleem relevant is en welk SEO- of beheerrisico ontstaat.
- Zo concreet mogelijk aangeven wat moet worden aangepast: bronpagina's, linkpatroon, template,
  canonical, redirect, robotsregel, sitemap of contentonderdeel.
- Benoemen wanneer juist geen wijziging nodig is en alleen menselijke beoordeling gevraagd wordt.
- Een verwachte eindsituatie en controle na implementatie geven: wat moet bij de volgende crawl
  veranderd zijn om het probleem als opgelost te bevestigen.
- Adviezen uitsluitend baseren op opgeslagen bewijs; onzekerheid zichtbaar houden en geen
  onbewezen AI-conclusie als feit presenteren.

### AI-ondersteunde verbetersuggesties

- Een modulaire AI-provider koppelen als advieslaag boven op crawl-, diagnose- en prestatiedata.
- Per paginatype vergelijkbare, goed presterende pagina's selecteren op basis van inhoud, zoekintentie
  en beschikbare GSC-, Bing- en verkeersdata; positie, merkbekendheid en andere vertekenende factoren
  expliciet meewegen.
- Voor titles, meta descriptions, headings, interne ankerteksten en structured data concrete
  conceptvoorstellen geven in plaats van alleen “verbeter dit” te tonen.
- Bij een meta-descriptionvoorstel tonen welke pagina-inhoud, zoekintentie en vergelijkingsgroep als
  basis zijn gebruikt, bijvoorbeeld: “op basis van deze drie vergelijkbare pagina's”.
- Twee of drie varianten kunnen geven met verschil in invalshoek, lengte en call-to-action.
- Bestaande merktaal en redactiestijl afleiden uit door de gebruiker goedgekeurde voorbeelden, niet
  uit willekeurige sitebrede tekst.
- Suggesties nooit automatisch publiceren; gebruiker laat kiezen, aanpassen, kopiëren, afwijzen of
  als actie opslaan.
- Afwijzingen en goedgekeurde varianten gebruiken als voorkeurssignaal zonder feitelijke crawlerdata
  of historische issues te overschrijven.
- Verzonden context minimaliseren, persoonsgegevens en secrets uitsluiten, kosten en gebruik per
  klant begrenzen en de AI-provider vervangbaar houden.
- Geen voorstel tonen wanneer broninhoud, zoekintentie of bewijs onvoldoende betrouwbaar is.

### UX/UI-polish

- Issues presenteren als diagnosekaart met samenvatting, waarom, waarschijnlijk probleem,
  concrete stappen, bewijs en verificatie in een duidelijke volgorde.
- Grote aantallen vergelijkbare URL's standaard groeperen en voorbeelden plus totaalomvang tonen.
- Tabellen richten op uitzonderingen en beslissingen; normale herhaling standaard samenvatten.
- Bron- en doelaantallen eenduidig benoemen, bijvoorbeeld drie links vanaf twee unieke pagina's.
- Technisch bewijs leesbaar formatteren en ruwe waarden pas op verzoek uitklappen.
- Dialogen, typografie, witruimte, filters, bulkacties, lege staten en mobiele weergave consistent
  nalopen.

### Bulk afhandelen en blijvend onthouden

- Issues selecteren via vinkjes, huidig filter, URL-groep of issuetype en gezamenlijk afhandelen.
- Twee expliciete bulkacties bieden:
  - `Opgelost; opnieuw controleren`: na de volgende crawl verifiëren en opnieuw openen wanneer het
    signaal nog of weer aanwezig is;
  - `Afgehandeld voor dit issuetype`: de combinatie website, URL en issuetype blijvend opslaan en
    hetzelfde signaal bij volgende crawls standaard negeren.
- Een blijvende afhandeling bewaren met gebruiker, datum, optionele toelichting en exacte scope.
- Andere issuetypen op dezelfde URL altijd normaal blijven tonen.
- Hetzelfde issuetype op nieuwe of niet-geselecteerde URL's altijd als nieuw issue tonen.
- Afgehandelde regels via een apart filter controleerbaar maken en individueel of in bulk kunnen
  herstellen.
- Bulkacties en automatische onderdrukking in de issuehistorie en auditlog vastleggen.

Acceptatie:

- De 404's op HUMAN-paginering worden als één patroon onderzocht en waar aantoonbaar als één
  waarschijnlijk paginerings-, filter- of canonicalprobleem gepresenteerd.
- `https://www.human.nl/artikelen/zo-bespreek-je-moeilijke-onderwerpen-in-de-klas-` verschijnt als
  één bronpaginadiagnose met alle drie of vier dode interne links, inclusief doel en ankertekst.
- Een overzicht met honderd URL's op crawldiepte 1 benoemt vooral de waarschijnlijke uitzonderingen.
- Ieder belangrijk issue beantwoordt: wat gebeurt er, waarom is dat relevant, wat is waarschijnlijk
  de oorzaak, wat moet concreet worden aangepast en hoe wordt de oplossing gecontroleerd.
- Een ontbrekende of zwakke meta description kan twee of drie direct bruikbare concepten opleveren,
  gebaseerd op de actuele pagina en aantoonbaar vergelijkbare goed presterende pagina's; de gebruiker
  ziet de onderbouwing en houdt altijd de eindbeslissing.
- Een gebruiker kan altijd onderscheid maken tussen feitelijk bewijs, systeeminterpretatie en een
  onzekere hypothese.
- De geselecteerde GrandVision-vacature- en favorieten-URL's kunnen voor één issuetype in bulk
  blijvend worden afgehandeld; hetzelfde type komt voor deze URL's niet terug, terwijl andere
  issuetypen en nieuwe URL's zichtbaar blijven.
- De interface toont vóór bevestiging hoeveel URL's, welk issuetype en welke blijvende reikwijdte
  de bulkactie krijgt.

Praktijktest bulkafhandeling:

- Vacature-ID's `29906`, `29820` en `29872`, inclusief merkvarianten onder GrandOptical en Pearle.
- De drie `/vacatures/favorieten`-varianten onder het hoofddomein, GrandOptical en Pearle.

## Fase 7 — Productieafronding

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

## Fase 8 — Schaalbaarheid en parallelle crawls

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

## Fase 9 — Matomo-integratie

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

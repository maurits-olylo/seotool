# Roadmap

Dit document is de actuele uitvoeringsplanning. `AGENTS.md` beschrijft de vaste werkwijze en
productvisie; `docs/architecture.md` beschrijft de technische werking. Een fase is pas afgerond
nadat de code is getest, gedeployed en het productieresultaat is gecontroleerd.

## Huidige status

- Actieve ontwikkellijn: fase 6 — intelligente diagnose en UX/UI-polish.
- Actueel releasepakket: consistente URL-uitsluitingen en begrensde filter-URL-discovery;
  technisch geïmplementeerd, volledige releasecontrole volgt.
- Productie: `https://seo.thact.nl` op Synology NAS `192.168.2.20`.
- Laatste lokale kwaliteitscontrole: 259 tests, Ruff, JavaScript-syntaxis en productie-Compose
  geslaagd.
- Multi-client domeinisolatie is op 2026-07-19 in productie bevestigd: `jobsatpearle.be` komt niet
  meer als actieve URL van `werkenbijgrandvision.nl` voor.

## Schaalbaarheid — crawl-admission en derde worker

Status: technisch in uitvoering.

- Maximaal één actieve, wachtende of gepauzeerde crawl per website.
- De scheduler maakt per cyclus hoogstens één werkelijk verschuldigde crawl per website.
- Een volledige crawl vervangt voor dezelfde periode een losse sitemap- en light check.
- Pending crawls blijven na refresh zichtbaar met FIFO-wachtrijpositie en workercapaciteit.
- Een derde NAS-worker wordt pas na deployment afzonderlijk gestart en onder belasting gemeten.

### Begrensde filter-URL-discovery

Status: geïmplementeerd en gedeployed; discovery-only issuebeleid technisch toegevoegd en nog
niet gedeployed.

- `ignored_query_parameters` geldt voor sitemapimport, handmatige registratie en intern ontdekte
  links en afbeeldingen.
- `excluded_url_patterns` gebruikt globpatronen tegen volledige URL, pad en query en voorkomt
  registratie en crawlen, terwijl de gevonden link als bewijs bewaard blijft.
- Per host en pad worden maximaal 100 URL-varianten met queryparameters gecrawld; overige
  varianten tellen als overgeslagen URL.
- Bestaande URL-records die door gewijzigde parameter- of uitsluitingsinstellingen samenvallen,
  worden inactief zonder historische snapshots te verwijderen.
- Een queryvariant die canonicaliseert naar exact hetzelfde pad zonder query blijft beschikbaar
  als discoverypagina: status, snapshot, links en assets worden bewaard.
- Discoverypagina's maken geen losse onpage-, element-, duplicate-, thin-content-, orphan-,
  diepte- of bronpagina-acties. Bestaande acties doorlopen bij de volgende volledige crawl de
  normale lifecycle naar opgelost.
- Bereikbaarheid, sitemapconflicten, paginatiecontrole en issues op de gevonden doelpagina's
  blijven actief.

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

Status: afgerond, gedeployed en op 2026-07-19 in productie gevalideerd.

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

### Geprioriteerde ontbrekende SEO-signalen

Status: gepland in onderstaande volgorde. Bestaande status-, redirect-, sitemap-, interne-link-,
onpage-, duplicate-, thin-content-, JobPosting- en alt-tekstcontroles blijven de basis.

1. **Google-indexstatus via URL Inspection**
   - Sla indexeringsstatus, laatste Google-crawl, Google-selected canonical, opgegeven canonical,
     robotsverdict en beschikbare rich-resultstatus op.
   - Vergelijk Google-keuzes met crawler-, sitemap- en canonicalbewijs.
   - Controleer belangrijke, gewijzigde en probleemverdachte URL's binnen de API-quota; geen
     onbeperkte inspectie van het volledige URL-register.
2. **Hreflang en internationale targeting**
   - Valideer taal-/landcodes, self-reference, retourverwijzingen en `x-default`.
   - Signaleer hreflangdoelen die redirecten, fouten geven, noindex zijn, robots-geblokkeerd zijn
     of naar een andere canonical wijzen.
   - Groepeer fouten per taalcluster of template in plaats van per losse URL.
3. **Soft 404's**
   - Combineer 200-status met foutteksten, vrijwel lege hoofdcontent, lege resultaten, canonical,
     redirects en historische paginastatus.
   - Maak alleen een hard probleem bij sterk gecombineerd bewijs; twijfelgevallen blijven review.
4. **Canonical-integriteit**
   - Detecteer meerdere canonicals, canonical naar foutstatus, redirect, noindex of geblokkeerde
     URL, en canonical chains of loops.
   - Vergelijk later met Google-selected canonical en groepeer systematische host-, protocol-,
     slash- en templatepatronen.
5. **Begrensde JavaScript-rendercontrole**
   - Render alleen verdachte, belangrijke of representatieve pagina's.
   - Vergelijk ontvangen en gerenderde content, links, canonical, robots en structured data.
   - Signaleer lege app-shells, ontbrekende rendercontent en links zonder crawlbare `a[href]`.
6. **Contextuele structured data buiten JobPosting**
   - Valideer vereiste velden en zichtbare-contentovereenkomst voor daadwerkelijk herkende
     paginatypen, zoals Product, Article, Organization, LocalBusiness, Event en VideoObject.
   - Controleer bereikbaarheid van schema-afbeeldingen en consistentie binnen een template.
   - Meld niet generiek dat ieder mogelijk schematype ontbreekt.
7. **Sitemap- en robotskwaliteit**
   - Controleer sitemap-URL's op robotsblokkade, noindex, niet-canonical status en onbereikbare
     child-sitemaps.
   - Beoordeel `lastmod` alleen bij aantoonbare structurele afwijking van inhoudswijzigingen.
   - Signaleer discovery-, filter- en functionele pagina's in sitemaps als patroonreview.
8. **Interne-linksemantiek**
   - Detecteer lege of niet-beschrijvende ankers, intern `nofollow`, uitsluitend template- of
     footerlinks en inconsistent ankergebruik voor belangrijke doelen.
   - Combineer dit later met zoekintentie om concurrerende URL's en ontbrekende inhoudelijke hubs
     te beoordelen.

Uitvoeringsregel:

- URL Inspection, hreflang en sterke canonicalconflicten mogen harde technische problemen
  opleveren bij direct bewijs.
- Soft 404, JavaScriptverschillen, structured-data-uitbreidingen, sitemapkwaliteit en
  interne-linksemantiek beginnen contextueel en gegroepeerd.
- Search intent en Lighthouse-aanbevelingen volgen hun eigen secties en worden niet als extra
  generieke SEO-score toegevoegd.

### Databronnenstrategie voor volledige SEO-analyse

Status: gepland als modulaire uitbreiding. Bronnen blijven herkenbaar en worden niet zonder
methodologische onderbouwing bij elkaar opgeteld.

Standaardbronnen:

1. **Technische toestand**
   - Gebruik crawler-, sitemap-, robots-, redirect-, canonical-, structured-data- en
     interne-linkbewijs als blijvende technische basis.
   - Voeg Google URL Inspection gericht toe voor belangrijke, gewijzigde en verdachte URL's.
2. **Zoekprestaties**
   - Gebruik GSC en Bing voor pagina-, zoekterm- en zichtbaarheidstrends.
   - Presenteer gemiddelden, dekking en meetverschillen expliciet; behandel positie niet als een
     exact ranktrackingresultaat.
3. **Bezoekersgedrag en conversie**
   - Ondersteun GA4 en Matomo gelijkwaardig als standaard analyticsbron; beide zijn optioneel en
     mogen naast elkaar gekoppeld zijn.
   - Houd definities en resultaten per bron gescheiden en laat per website een primaire bron voor
     opportunity-prioritering kiezen.
4. **Ervaring en performance**
   - Combineer CrUX-velddata met begrensde Lighthouse/PageSpeed-metingen op representatieve,
     belangrijke of probleemverdachte pagina's.
   - Zet technische audits om in website- en templatespecifieke acties.

Verdiepende bronnen:

- **Bedrijfswaarde:** koppel later formulieren, calltracking, ecommerce of CRM aan landingspagina's
  om leads, omzet en gekwalificeerde conversies mee te wegen.
- **Googlebotgedrag:** importeer optioneel geanonimiseerde server- of CDN-logs voor werkelijk
  crawlgedrag, crawlbudgetverspilling en bot-specifieke fouten.
- **SERP en rankings:** gebruik een externe leverancier voor locatie-, apparaat-, SERP-feature- en
  concurrentiedata wanneer GSC onvoldoende is.
- **Autoriteit:** gebruik een volwaardige externe backlinkbron voor nieuwe, verloren en relevante
  links; lege Bing-linkdata blijft onvoldoende bewijs.
- **Contentbeheer:** koppel waar zinvol CMS-metadata zoals paginatype, eigenaar, publicatiedatum,
  template en workflowstatus.
- **Verticale bronnen:** maak Google Business Profile, Merchant Center en Google Ads optionele
  modules voor respectievelijk lokale, ecommerce- en betaalde zoekcontext.

Commerciële afbakening:

- Crawl, GSC, Bing en GA4 of Matomo horen bij de standaardpropositie.
- URL Inspection en een begrensde Lighthouse/CrUX-dekking horen bij inhoudelijk rijkere pakketten.
- CRM, serverlogs, externe ranktracking, SERP- en backlinkdata zijn specialistische uitbreidingen
  wegens implementatie-, licentie- of verwerkingskosten.
- Prijs en capaciteit worden begrensd op unieke relevante URL's, analysefrequentie, bewaartermijn
  en kostbare verwerking; niet op het aantal gevonden issues.

### Search intent en paginafunctie

Status: gepland na de huidige contextuele issue- en ruisreductie en vóór de modulaire AI-advieslaag.

- Zoekintentie en paginafunctie afzonderlijk modelleren. Zoekintentie ondersteunt minimaal
  informatief, commercieel onderzoek, transactioneel, navigerend en lokaal; paginafunctie
  ondersteunt minimaal landingspagina, categorie/overzicht, product/dienst/vacature,
  artikel/nieuws, contact/conversie en functionele/discoverypagina.
- Begin met een uitlegbare classificatie op basis van URL, title, H1, hoofdcontent, schema,
  interne ankerteksten en bestaand paginatype. Gebruik GSC-zoekopdrachten als sterkste bewijs
  voor de werkelijk waargenomen zoekintentie.
- Sla confidence, gebruikte bewijssignalen en analysemoment op. Zonder voldoende GSC- of
  contentsignalen blijft de conclusie voorlopig en controlegericht.
- Ondersteun een handmatig ingestelde verwachte intentie en paginafunctie die automatische
  classificatie overrulen zonder de gemeten signalen te verwijderen.
- Maak alleen bruikbare diagnoses voor een aantoonbare intentiemismatch, concurrerende URL's,
  gemengde intentie of een ontbrekende passende landingspagina. Start deze als `review`, niet als
  automatisch hard probleem.
- Sluit functionele en discovery-only pagina's uit van reguliere intentacties. Gebruik geen
  generieke intentscore.

Uitvoeringsvolgorde:

1. Taxonomie, handmatige verwachte intentie/paginafunctie en bewijsmodel.
2. Automatische waargenomen intentie uit crawlgegevens en beschikbare GSC-query's.
3. Confidence-drempels, mismatch-, cannibalisatie- en contentkansdiagnoses.
4. Later optionele AI-verrijking voor twijfelgevallen en adviestekst; AI is geen vereiste voor de
   feitelijke classificatie.

Acceptatie:

- Iedere intentieconclusie toont waarom zij is getrokken en welke bron het zwaarst weegt.
- Een handmatige keuze blijft behouden na nieuwe analyses.
- Pagina's zonder voldoende bewijs leveren geen harde actie op.
- Meerdere URL's worden alleen als intentieconcurrenten getoond bij aantoonbare overlap in GSC-
  query's of sterke inhoudelijke en structurele overeenkomst.

### Data-gedreven opportunity-engine

Status: gepland na de betrouwbare issue- en ruislaag. Eerste versie werkt zonder AI en wordt later
verrijkt met search intent en Lighthouse-bewijs.

Doel:

- Herken pagina's en URL-families waar aantoonbaar zoek- of conversiepotentieel wordt beperkt door
  één of meer samenhangende, oplosbare fricties.
- Verhoog de prioriteit van een kans niet door issues simpel op te tellen, maar door het verband
  tussen potentieel, blokkade, bewijskracht en verwachte inspanning uit te leggen.
- Presenteer kansen binnen het bestaande actieplatform zonder generieke website- of SEO-score.

Beoordelingsdimensies:

1. **Potentieel** — GSC-impressies, positie, CTR, organisch verkeer, conversies, paginatype,
   historische trend en handmatige belangrijkheid.
2. **Frictie** — relevante technische, inhoudelijke, interne-link-, indexatie-, intentie- en
   performanceproblemen die het gemeten potentieel aannemelijk beperken.
3. **Bewijskracht** — datavolume, meetperiode, consistentie tussen bronnen, actualiteit en
   confidence van de onderliggende signalen.
4. **Inspanning en bereik** — kleine pagina-aanpassing, gedeelde component, templatecorrectie of
   groter technisch project, plus het aantal geraakte waardevolle pagina's.

Eerste opportunity-patronen:

- Veel impressies en positie 4–15 combineren met lage CTR en aantoonbaar zwakke title- of
  snippetinformatie.
- Positie 11–20 combineren met passende paginafunctie, duidelijke inhoudelijke lacune en voldoende
  bestaande vraag.
- Organisch verkeer of conversies combineren met hoge crawldiepte of zwakke relevante interne
  ondersteuning.
- Een kleine templatecorrectie koppelen aan meerdere pagina's met gezamenlijk groot organisch of
  conversiepotentieel.
- Een prestatiedaling koppelen aan een relevante recente metadata-, canonical-, indexatie-,
  content- of interne-linkwijziging.
- Overlappende GSC-query's en vergelijkbare content koppelen aan een consolidatie- of
  differentiatiekans.
- Lighthouse-frictie later zwaarder prioriteren op pagina's met aantoonbaar verkeer, conversies of
  zoekpotentieel.

Bescherming tegen schijnkansen:

- Gebruik minimale drempels voor impressies, klikken, conversies en meetduur.
- Corrigeer waar mogelijk voor merkqueries, seizoen, paginatype, websiteomvang en bekende
  campagnes of wijzigingen.
- Sluit discovery-only en functionele pagina's standaard uit.
- Respecteer handmatige belangrijkheid, suppressions, geaccepteerd risico en bewuste
  pagina-intentie.
- Maak geen kans wanneer de blokkade niet aannemelijk samenhangt met het gemeten potentieel.

Presentatie:

- Toon vier visuele deelscores van 0–100 voor potentieel, beïnvloedbare frictie, bewijskracht en
  uitvoerbaarheid/bereik, met per score de gebruikte periode, databronnen en berekening.
- Toon daarnaast één transparante kansscore en een prioriteitsklasse zoals `hoge kans`, `kans`,
  `monitoren` of `onvoldoende bewijs`. Dit is geen algemene SEO-gezondheidsscore en voorspelt geen
  percentage extra verkeer.
- Leg per kans uit welk potentieel bestaat, welke fricties samenhangen, waarom de conclusie
  betrouwbaar is, wie de actie kan uitvoeren en hoe resultaat wordt gecontroleerd.
- Toon de onderliggende issues, metrics en wijzigingen als bewijs en behoud hun eigen lifecycle.
- Groepeer kansen per pagina, URL-familie of gedeelde oorzaak en voorkom dubbele acties.
- Visualiseer de deelscores als compacte balken en toon patronen als bewijskaarten, bijvoorbeeld
  `CTR-kans`, `pagina-twee-kans`, `interne-link-kans`, `templatekans`, `herstelkans`,
  `cannibalisatiekans` en `performancekans`.
- Toon positieve en negatieve bijdragers afzonderlijk, bijvoorbeeld veel relevante impressies,
  positie dicht bij pagina één, bestaande conversies, seizoensinvloed of onvoldoende recente data.
- Behandel ontbrekende data als `onbekend` en niet automatisch als nul. Toon datadekking en
  vergelijk waar mogelijk met de vorige meetperiode.

Eerste uitlegbare weging:

- Potentieel: 40%.
- Beïnvloedbare frictie: 25%.
- Bewijskracht: 20%.
- Uitvoerbaarheid en bereik: 15%.
- Een minimale bewijskracht begrenst de maximale kansscore en prioriteitsklasse, zodat weinig data
  nooit tot een hoge kans kan leiden.
- Maak gewichten en drempels centraal versioneerbaar. Bewaar per berekening de gebruikte
  formuleversie, zodat historische scores verklaarbaar en vergelijkbaar blijven.

Acceptatie:

- Dezelfde kleine issue krijgt aantoonbaar verschillende prioriteit op een waardevolle en een
  onbelangrijke pagina.
- Iedere hoge kans bevat meetbaar potentieel en minimaal één aannemelijk beïnvloedbare frictie.
- Een gebruiker kan zonder AI herleiden welke feiten tot de kans en prioriteitsklasse leidden.
- Iedere deel- en totaalscore kan volledig worden teruggeleid naar genormaliseerde bronwaarden,
  bijdragers, drempels en formuleversie.
- Pagina's van verschillende klanten of onvergelijkbare paginatypen worden niet misleidend tegen
  elkaar gebenchmarkt.
- Na uitvoering kan de tool zowel het verdwijnen van de frictie als de ontwikkeling van verkeer,
  zichtbaarheid of conversies volgen zonder direct causaliteit te claimen.

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

Status: afgerond, gedeployed en op 2026-07-19 met HUMAN gevalideerd. De officiële API leverde
pagina- en zoektermdata maar geen backlinkdekking; de volledige handmatige exporthistorie bleef
correct behouden.

- Bing-pagina- en zoektermstatistieken versleuteld geauthenticeerd en idempotent importeren.
- Bing-URL's aan het blijvende URL-register koppelen en importdekking tonen.
- Inkomende linkaantallen, verwijzende pagina's en ankerteksten importeren; eerste en laatste
  waarneming bewaren en verdwenen links alleen bij volledige hercontrole markeren.
- Handmatige import en dagelijkse synchronisatie ondersteunen met blijvende foutstatus.
- Dalende Bing-zichtbaarheid naast Google-inzichten tonen en databron expliciet benoemen.
- Geen scraping-workaround voor ontbrekende officiële functionaliteit.

Acceptatie:

- HUMAN importeert pagina- en zoektermregels zonder duplicaten bij herhaling.
- HUMAN importeert linkdoelen en inkomende linkdetails zonder duplicaten; gedeeltelijke
  API-dekking wordt zichtbaar en leidt niet tot valse verdwenen-links-signalen.
- Bekende HUMAN-URL's worden aan het URL-register gekoppeld; afwijkende URL's blijven als
  controleerbare ongekoppelde regels bewaard.
- Een Bing-daling wordt als Bing-signaal getoond en niet stilzwijgend met GSC-data vermengd.
- Een ingetrokken token of API-fout verschijnt als herstelbare integratiefout zonder geheimen.

## Fase 6 — Intelligente diagnose en UX/UI-polish

Status: in uitvoering; sitemapredirects, interne redirects, gelijktijdige 5xx-responses,
vacaturetemplates, thin content en crawldiepte worden inmiddels contextueel beoordeeld.
Productievalidatie van dit pakket volgt.

### SEO-issues en kwaliteitscontroles expliciet onderscheiden

Status: eerste scopeclassificatie op 2026-07-19 gedeployed en in productie gevalideerd.

- API en interface onderscheiden SEO, SEO+UX, kwaliteitscontrole, performance en redactioneel.
- Afbeeldings-, kopstructuur- en dieptesignalen staan niet langer zonder voorbehoud als SEO-fout.
- Bestandsgrootte wordt als performancecontrole en mogelijke contentouderdom als redactionele
  controle gepresenteerd.
- Scope wordt afgeleid uit issuetype, zodat bestaande historie zonder migratie correct is gelabeld.
- De actielijst onderscheidt daarnaast aantoonbare problemen, contextafhankelijke controles en
  optionele optimalisaties volgens de goedgekeurde audit.
- Lange redirectketens hebben lage prioriteit en vacature-identifierrisico is een
  kwaliteitsoptimalisatie; hiermee zijn de statische auditclassificaties verwerkt.

### Van signaal naar diagnose

- Losse URL-signalen clusteren tot één waarschijnlijk onderliggend probleem.
- Vergelijkbare vacatures zonder identifier als één websitebrede templatediagnose tonen, met
  vacatureclusters, overlap en alle geraakte URL's als bewijs.
- Exact gelijke vacaturecontent eerst op contenthash groeperen, zodat algemene templatewoorden de
  conservatieve bijna-duplicaatfilter niet kunnen laten missen dat pagina's aantoonbaar gelijk zijn.
- URL-patronen herkennen, waaronder paginering, filters, facetten, parameters, templates en
  canonical- of redirectconfiguraties.
- Paginering- en parameterreeksen die meerdere 404's veroorzaken als één websitebrede diagnose
  tonen; onderliggende URL-issues voor historie bewaren maar niet als dubbele hoofdtaken tonen.
- Genummerde eindslugs vanaf drie geraakte 404-URL's als één reeksdiagnose tonen; losse paren,
  jaartallen en UUID's blijven afzonderlijk om overgroepering te voorkomen.
- Lichte checks behouden de specifiekere 404-context uit de laatste volledige crawl en openen niet
  daarnaast opnieuw een generieke 404-taak voor dezelfde URL.
- Vergelijkbare paginagroepen vormen en afwijkingen binnen zo'n groep aanwijzen in plaats van alle
  normale waarden als losse regels te tonen.
- Grote URL-families met dezelfde metadata-, canonical-, content-, H1-, diepte- of orphancontrole
  als templateclusters presenteren; kleine groepen en afwijkende URL's blijven afzonderlijk.
- Pagineringsreeksen bundelen metadata-, canonical-, diepte- en grensfouten tot één templatecontrole;
  onderliggende URL-signalen blijven historisch bewaard maar verdwijnen uit de hoofdactielijst.
- Crawldiepte, indexatie, interne links, wijzigingen, schema en verkeersdata gezamenlijk beoordelen.
- Mogelijke hoofdoorzaak, alternatieve verklaring, vertrouwen en technisch bewijs apart tonen.
- Eén hoofdissue koppelen aan geraakte URL's en onderliggende signalen zonder historie te verliezen.
- Interne-linkproblemen ook vanuit de bronpagina groeperen: één pagina met meerdere dode uitgaande
  links wordt één diagnose met de afzonderlijke doelen als bewijs, niet meerdere losse hoofdissues.
- Per defecte link doel-URL, ankertekst, status/fout, eerste waarneming en aanbevolen vervanging of
  verwijdering tonen.
- Zowel bronpatronen als doelpatronen ondersteunen: meerdere defecte links op één pagina en één
  defect doel waar veel pagina's naartoe linken zijn verschillende, maar gerelateerde diagnoses.
- Bronpagina's met minimaal twee redirectlinks als één onderhoudstaak tonen; de onderliggende
  redirectdoelen blijven historisch bewaard en enkelvoudige gevallen blijven afzonderlijk zichtbaar.
- Sitemapredirects vanaf drie URL's per aantoonbare transformatie als één configuratieactie tonen;
  een trailing slash is daarbij geen fout, de redirectende sitemapvermelding is het signaal.
- Interne redirects vanaf drie gelijksoortige URL-omzettingen als één component-, navigatie- of
  migratieactie tonen; URL-gecodeerde CMS-placeholders niet als redirect classificeren.
- Drie of meer gelijke 5xx-responses uit één crawl als mogelijk tijdelijk incident presenteren en
  eerst met logs en een light check laten bevestigen.
- Thin content alleen melden voor vrijwel lege indexeerbare contentpagina's of duidelijke
  contextuele uitschieters binnen een voldoende grote URL-familie of website.
- Diepte 4 en 5 alleen tonen voor belangrijke of zwak intern gelinkte pagina's; diepte 6 of hoger
  blijft als uitzonderlijke structuurcontrole zichtbaar.
- Herhaalde JobPosting-templatefouten groeperen wanneer minimaal drie vacaturepagina's hetzelfde
  schema- of toepassingssignaal delen.
- De gecombineerde templatediagnose opsplitsen naar één gerichte clusteractie per issuetype;
  orphan-families vanaf twee URL's groeperen en de legacy-megadiagnose via de lifecycle oplossen.
- Ontbrekende alt-attributen als kwaliteitsprobleem tonen met exact afbeeldingselementbewijs.
  Lege alt-teksten alleen melden bij een onbenoemde functionele afbeelding; correcte decoratieve,
  verborgen en trackingafbeeldingen blijven stil.

### Van diagnose naar exact handelingsadvies

Status: eerste bewijsgebonden versie gereed op 2026-07-18. Ieder issuedetail levert een vaste
structuur voor relevantie, waarschijnlijke oorzaak, alternatieve verklaring, concrete actie en
verificatie. Feitelijke metingen, systeeminterpretaties en hypotheses worden zichtbaar van elkaar
onderscheiden. Productievalidatie liet zien dat generieke oorzaak- en hypotheseteksten geen waarde
toevoegen; sinds de correctie worden deze secties alleen getoond wanneer opgeslagen diagnosebewijs
bestaat. Verdere issuetype-specifieke verdieping volgt samen met nieuwe diagnoses.

- Uitleggen waarom het probleem relevant is en welk SEO- of beheerrisico ontstaat.
- Zo concreet mogelijk aangeven wat moet worden aangepast: bronpagina's, linkpatroon, template,
  canonical, redirect, robotsregel, sitemap of contentonderdeel.
- Benoemen wanneer juist geen wijziging nodig is en alleen menselijke beoordeling gevraagd wordt.
- Een verwachte eindsituatie en controle na implementatie geven: wat moet bij de volgende crawl
  veranderd zijn om het probleem als opgelost te bevestigen.
- Adviezen uitsluitend baseren op opgeslagen bewijs; onzekerheid zichtbaar houden en geen
  onbewezen AI-conclusie als feit presenteren.

#### Lighthouse-aanbevelingen als uitvoerbare websiteacties

Status: gepland als API-integratie en adviesbron; geen afzonderlijk SEO-score- of
Lighthouse-dashboard.

- Importeer mislukte Lighthouse-audits, betrokken bestanden en elementen, mogelijke besparing,
  categorie en Lighthouse-versie via de PageSpeed Insights API.
- Gebruik scores en labmetingen alleen als ondersteunend bewijs voor prioriteit en voortgang.
  Maak niet automatisch een losse actie omdat een categorie- of auditscore onder een generieke
  grens ligt.
- Combineer Lighthouse-bewijs met crawlerdata, paginatype, URL-familie, templateclusters,
  elementlocaties en bekende externe bronnen. Bepaal zo of de oorzaak bij één pagina, component,
  template, CMS-instelling of externe dienst ligt.
- Groepeer dezelfde audit over meerdere URL's tot één actie per waarschijnlijke oorzaak. Maak geen
  actie per URL en audit.
- Presenteer iedere actie in vaste, toegankelijke lagen:
  1. wat er gebeurt en wat een bezoeker daarvan merkt;
  2. waar de aanpassing waarschijnlijk moet plaatsvinden;
  3. wie dit kan uitvoeren: beheerder, contentredacteur of developer;
  4. concrete implementatiestappen voor deze website;
  5. geraakte URL's, templates, bestanden of elementen;
  6. controle waarmee de oplossing kan worden bevestigd.
- Toon ruwe audit-ID's, meetwaarden, resources, selectors en Lighthouse-details pas onder
  `Technisch bewijs`.
- Geef alleen websitespecifieke implementatiestappen wanneer CMS, frontendpatroon of technisch
  bewijs voldoende duidelijk is. Benoem anders welke informatie nog ontbreekt; verzin geen
  implementatiedetails.
- Behandel performance-, toegankelijkheids- en best-practice-aanbevelingen als verbeteracties
  binnen het bestaande actieplatform, niet automatisch als SEO-probleem.

Eerste bruikbare scope:

- afbeeldingen comprimeren, correct schalen en moderne formaten gebruiken;
- onnodige of ongebruikte JavaScript- en CSS-belasting verminderen;
- render-blocking resources en kritieke laadvolgorde verbeteren;
- caching, fonts en externe scripts doelgerichter configureren;
- LCP-resource en serverreactietijd verbeteren wanneer Lighthouse voldoende oorzaakinformatie
  levert.

Acceptatie:

- Een niet-technische gebruiker begrijpt wat moet veranderen en wie daarvoor nodig is.
- Eén gedeelde templateoorzaak verschijnt als één actie met geraakte voorbeelden.
- Iedere stap is herleidbaar tot Lighthouse- en crawlerbewijs.
- De gebruiker kan na uitvoering gericht controleren of de oorzaak en niet alleen de score is
  verbeterd.

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

Productiebevinding 2026-07-18: het issuedetail deed circa vijf seconden over een antwoord doordat
elementbewijs en verkeersimpact voor de volledige crawl en website werden geladen. De detailquery
is beperkt tot de gekozen URL en het betrokken doel, en de dialoog opent direct met laadstatus.
Productiemeting na deployment bepaalt of verdere indexering of caching nodig is.

- Issues presenteren als diagnosekaart met samenvatting, waarom, waarschijnlijk probleem,
  concrete stappen, bewijs en verificatie in een duidelijke volgorde.
- Grote aantallen vergelijkbare URL's standaard groeperen en voorbeelden plus totaalomvang tonen.
- Tabellen richten op uitzonderingen en beslissingen; normale herhaling standaard samenvatten.
- In het URL-overzicht actieve signalen direct naast de URL tonen, met hoogste prioriteit en
  belangrijkste diagnose, zodat status en crawldiepte niet zonder inhoudelijke context staan.
- Bron- en doelaantallen eenduidig benoemen, bijvoorbeeld drie links vanaf twee unieke pagina's.
- Technisch bewijs leesbaar formatteren en ruwe waarden pas op verzoek uitklappen.
- Dialogen, typografie, witruimte, filters, bulkacties, lege staten en mobiele weergave consistent
  nalopen.

### Live elementlokalisatie uitbreiden

Status: eerste versie technisch geïmplementeerd; productievalidatie na een nieuwe volledige crawl.

- Ondersteuning uitbreiden naar meer bestaande en betrouwbaar lokaliseerbare elementen.
- Betere herkenning en tekstcontext gebruiken wanneer dezelfde zichtbare tekst vaker voorkomt.
- Altijd terugvallen op bronpagina, HTML-fragment, CSS-selector en XPath wanneer geen veilige
  URL-jump bestaat.
- Browser- en compatibiliteitstests uitvoeren voor element-ID's en text-fragment-URL's.
- Een expliciete betrouwbaarheidsscore toevoegen voor live URL-jumps.
- Nooit een locatieknop tonen voor ontbrekende elementen waarvoor geen bestaand DOM-doel bestaat.

Acceptatie eerste versie:

- Issue-details tonen per betrokken bestaand element type, tekst, doel-URL en technische context.
- Een stabiel element-ID heeft voorrang; daarna volgt alleen unieke tekst of unieke prefix/suffix.
- Interne 404- en redirectlinks, linkplaceholders, dubbele headings, defecte CTA's en gebroken
  afbeeldingen kunnen locatiebewijs opslaan.
- Icon-only, lege en dubbele elementen zonder unieke context krijgen geen misleidende jumpknop.

### Bulk afhandelen en blijvend onthouden

Status: gereed op 2026-07-18. De database, bulk-API, exacte onderdrukking in de issue-engine,
auditregistratie, selectievakjes, selectie op het huidige filter, zichtbare feedback, lijstweergave
en individueel herstel zijn beschikbaar. Bulkherstel van meerdere afgehandelde regels tegelijk kan
later worden toegevoegd wanneer de praktijk daar behoefte aan toont.

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
- Een groot aantal GrandVision-vacatures zonder identifier verschijnt alleen als één diagnose
  wanneer aantoonbare gelijkende clusters bestaan; optionele velden zonder risico blijven stil.
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

- Git op de Synology NAS installeren en read-only of minimaal bevoegde GitHub-authenticatie voor
  deployments configureren; daarna updates vanuit de productiemap met `git pull --ff-only`
  uitvoeren.
- Tot Git en GitHub-authenticatie op de NAS beschikbaar zijn, releases op de Mac vanaf een exacte
  commit als archive maken, de SHA-256 vastleggen, het pakket via SSH naar de NAS uploaden en pas na
  checksumcontrole uitpakken.
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

Status: begrensde light- en full-crawlpools draaien in productie; afzonderlijke operationele
wachtrij-informatie is lokaal geïmplementeerd.

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

Status: gepland als standaard analyticskoppeling naast GA4. De Bing Webmaster Tools-integratie is
hervat en gevalideerd, waardoor Matomo inhoudelijk ingepland kan worden zodra de huidige
stabiliteits- en issuekwaliteitspakketten zijn afgerond.

- Een Matomo-site koppelen via server-URL, `idSite` en een API-token met leestoegang.
- API-tokens versleuteld bewaren en uitsluitend via POST versturen, nooit in URL's of logs.
- Bezoeken, paginaweergaven, landingspagina's, verkeersbronnen, doelen en conversies importeren.
- Matomo-pagina's via genormaliseerde URL's aan het blijvende URL-register koppelen.
- Issues en wijzigingen verrijken met verkeers- en conversie-impact, gelijkwaardig aan GA4-data.
- Matomo naast GA4 ondersteunen; geen van beide integraties verplicht maken.
- Per website een primaire analyticsbron voor opportunity-prioritering kiezen en cijfers van GA4
  en Matomo nooit stilzwijgend optellen.

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

## Fase 10 — Volwaardige visuele issue-inspectie

Status: toekomstig; laatste brede productfase na de huidige roadmap.

- Een eigen inspectiemodus bouwen die opgeslagen of opnieuw gerenderde pagina's binnen SEO Monitor
  toont, automatisch naar het betrokken element scrolt en issues met overlays markeert.
- Zowel bestaande als ontbrekende elementen ondersteunen, waaronder ontbrekende H1's,
  alt-attributen, CTA's, formulierlabels en breadcrumbs.
- Gebroken afbeeldingen, headingproblemen, interne 404-links, redirects en
  schema-contentmismatches visueel aanwijzen.
- Accessibilityproblemen, LCP-elementen, layout shifts en overlappende pop-ups of sticky elementen
  in dezelfde inspectiestroom opnemen.
- Opgeslagen crawlbewijs en optionele her-rendering scheiden, zodat zichtbaar blijft welk bewijs
  historisch is en wat live opnieuw is vastgesteld.

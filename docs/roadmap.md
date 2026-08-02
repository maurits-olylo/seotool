# Roadmap

Dit document is de actuele uitvoeringsplanning. `AGENTS.md` beschrijft de vaste werkwijze en
productvisie; `docs/architecture.md` beschrijft de technische werking. Een fase is pas afgerond
nadat de code is getest, gedeployed en het productieresultaat is gecontroleerd.

## Huidige status

- Actieve ontwikkellijn: Release 3 voor URL Inspection, hreflang en canonical-integriteit. Publieke
  website-inschatting en friends-and-family volgen in Release 13.
- Productie en de geïsoleerde NAS-stagingomgeving zijn gezond en staan op migratie `0037`.
- De elementlocatie-cleanup is op 1 augustus 2026 afgerond en operationeel gecontroleerd.
- Automatische elementlocatieretentie is op 1 augustus 2026 in productie gevalideerd: vijf
  persistente operaties zijn geslaagd en één operatie hervatte zichzelf begrensd via scheduler en
  maintenancequeue.
- Laatste volledige lokale kwaliteitscontrole: 352 tests geslaagd en Ruff zonder bevindingen.
- Multi-client domeinisolatie is op 2026-07-19 in productie bevestigd: `jobsatpearle.be` komt niet
  meer als actieve URL van `werkenbijgrandvision.nl` voor.

## Gebundelde uitvoeringsplanning vanaf 2 augustus 2026

De resterende roadmap wordt voortaan in grotere, samenhangende releases uitgevoerd. De bestaande
secties hieronder blijven de inhoudelijke specificatie en behouden hun gerealiseerde status. Deze
releasevolgorde is leidend voor planning en deployment. Interne mijlpalen worden niet afzonderlijk
gedeployed; per release volgt één integrale kwaliteitscontrole, stagingproef en productiedeployment.

1. **Retentie en productie-integriteit** — versieerbaar beleid, volledige audit, veilige
   multi-datasetretentie en bewijsbehoud. Status: afgerond en op 2 augustus 2026 met migratie
   `0036` op staging en productie gevalideerd. Alle 45 productieoperaties voor vijf websites en
   negen datasets eindigden als `succeeded`; 185.741 oude, onbeschermde elementlocaties zijn
   verwijderd, de audit is opgeslagen, API en database zijn gezond en de crawl-drain is opgeheven.
2. **Queuecapaciteit en operationele stabiliteit** — admission, prioriteiten, backpressure,
   dead-letter-afhandeling, sitemapregressies en resterend runbook. Status: afgerond en op
   2 augustus 2026 met migratie `0037` op staging en productie gevalideerd. Het versieerbare
   queuebeleid, websiteprioriteiten, toelatingsgrenzen, aparte sitemapqueue, prioriteitsgestuurd
   hervatten, duurzame dead letters, superuserherstel, systeemstatus, operationele UI,
   sitemapregressies en het incidentrunbook zijn actief. De productievalidatie bevestigde
   policyversie `2026-08-02-v1`, een gezonde API en database en een correct opgeheven crawl-drain.
3. **URL Inspection, hreflang en canonical-integriteit.** Fase 1 is lokaal geïmplementeerd:
   snapshots bewaren alle canonical-tags en hreflangverwijzingen, wijzigingen tellen mee in de
   metadatahash en migratie `0038` voegt een historisch URL Inspection-resultaatmodel toe. Externe
   Google-aanroepen, selectiebeleid, validatie en issuegroepering volgen in de volgende fasen.
4. **Soft 404, begrensde JavaScript-rendering en asset-/mediaregister.**
5. **Lighthouse/CrUX, contextuele structured data en sitemap-/robotskwaliteit.**
6. **Begrijpelijk actieplatform** — diagnoses, taken, URL-overzicht, crawldiepte, exports,
   notificaties en UX/UI-polish.
7. **Matomo en analytics-meetkwaliteit.**
8. **Zoekintentie en contentanalyse** — kwaliteit, veroudering, overlap en interne-linkkansen.
9. **Opportunity-engine en contextuele data-assistent.**
10. **Genormaliseerde externe links en eerste betaalde dataprovider.**
11. **SERP-, zichtbaarheid- en concurrentieanalyse.**
12. **Effectmeting en klant-/managementrapportage.**
13. **Publieke ervaring en onboarding** — website-inschatting, publieke vraagassistent,
    vergelijkingen, invitation-only onboarding, websiteverificatie en meetvalidatie.
14. **Begrensde generatieve AI** — providerabstractie, gebruiksregistratie, budgetten,
    prijsbevestiging, audit, veiligheidsregels en alleen goedgekeurde kleine functies.

Grote releases betekenen niet dat onverenigbare risico's ongescheiden worden uitgevoerd. Iedere
migratie blijft herhaalbaar en controleerbaar. Destructieve dataverwerking, providerkosten en
commerciële prijsbesluiten krijgen binnen de release een expliciete gate. De volledige vergelijking
met de aangeleverde roadmap staat in `docs/roadmap-coverage-2026-08-02.md`. De daarin gemarkeerde
uitbreidingen, nieuwe modules en aanvullende acceptatieregels zijn een normatieve bijlage bij deze
roadmap en behoren tot de resterende scope.

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

Status: geïmplementeerd, gedeployed en op 1 augustus 2026 in productie gevalideerd.

- Ingestelde sitemaps aanvullen met sitemapverwijzingen uit `robots.txt`.
- Zonder verwijzing gecontroleerd `/sitemap.xml` proberen.
- Automatisch gevonden sitemapadressen voor volgende jobs bewaren.
- Unieke gevonden URL's en gelezen sitemapdocumenten tellen.
- Een job zonder beschikbare sitemap niet langer leeg als geslaagd tonen.
- Tot 1.000 unieke sitemapdocumenten verwerken, zodat grote maar geldige sitemapindexen zoals die
  van HUMAN volledig worden ingelezen.
- Bij overschrijding van de veiligheidslimiet nooit stil afkappen, maar de job als deels geslaagd
  markeren met het aantal nog niet verwerkte documenten.
- De productievalidatie met HUMAN verwerkte 193 sitemapdocumenten in circa 49 seconden en vond
  3.745 unieke URL's. De eerdere limiet van 100 documenten vond slechts 2.789 URL's; de correctie
  maakte daardoor 956 aanvullende URL's zichtbaar.

### Visuele vernieuwing publieke website

Status: afgerond, gedeployed en geaccepteerd.

- Bestaande kleuren en typografie behouden.
- Ruimere hero en productvisual toevoegen vóór de login.
- Sticky uitleg links koppelen aan scrollende productbeelden rechts.
- Prioriteiten, veranderingen, sitestructuur en actiebeheer uitleggen.
- Het ingelogde dashboard functioneel en compact houden.

### Contextuele JobPosting-identifiers

Status: geïmplementeerd, gedeployed en op 1 augustus 2026 in productie gevalideerd.

- Ontbrekende aanbevolen velden niet zelfstandig als waarschuwing tonen.
- Vacatures zonder identifier sitebreed op sterke inhoudelijke gelijkenis vergelijken.
- Alleen bij aantoonbaar verwarringsrisico een contextueel issue maken.
- Groepsgrootte, overlap en gerelateerde URL's als technisch bewijs tonen.
- Vanaf vijf vergelijkbare vacatures de prioriteit van laag naar middel verhogen.
- De actieve productie-worker bevat de contextuele analyse. In productie missen 28 actieve,
  indexeerbare vacatures van Schipper Kozijnen en 507 van GrandVision een identifier zonder dat dit
  op zichzelf losse waarschuwingen oplevert.
- GrandVision leverde één aantoonbaar overlapcluster van twee vacatures op met bron
  `cross_vacancy_similarity`, lage prioriteit en volledig clusterbewijs. Een latere geslaagde
  volledige crawl verifieerde het issue; een aanvullende crawl of herberekening was niet nodig.

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
   - Signaleer overfragmentatie contextueel wanneer veel child-sitemaps structureel zeer weinig
     URL's bevatten; het aantal sitemapbestanden alleen is geen harde SEO-fout.
   - Detecteer lege of dubbele child-sitemaps, ontbrekende `lastmod`-waarden in sitemapindexen en
     ongeldige epoch-fallbacks rond 1970 als afzonderlijk technisch bewijs.
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

### Zoekintentie & klantreis

Status: gepland als fase 10, direct na de Matomo-integratie en vóór de modulaire AI-advieslaag.
De volledige module wordt niet tijdens de huidige ruis- en diagnosefase gebouwd.

De module combineert drie afzonderlijke, uitlegbare dimensies per indexeerbare canonical URL:

- zoekintentie: informatief, commercieel oriënterend, transactioneel, vertrouwen, navigatie of
  gemengd/onzeker;
- klantreisfase: ontdekken, begrijpen, overwegen, vergelijken, beslissen, handelen, nazorg of
  onzeker;
- strategische contentrol, zoals verkeer aantrekken, keuze ondersteunen, bewijs leveren,
  converteren, navigeren of bestaande klanten ondersteunen.

Crawlerdata bepaalt de waarschijnlijke contentintentie. GSC-query's tonen waarvoor een pagina
daadwerkelijk vertoningen en klikken ontvangt. De primaire analyticsbron toont geobserveerde
landingspagina's, vervolgstappen en conversies. Google levert zelf geen intentielabel; iedere
conclusie blijft daarom een modelschatting met confidence, brondekking, versie en bewijs.

Randvoorwaarden:

- Geen algemene SEO-score, verplichte lineaire funnel of universele norm voor contentverdeling.
- Classificeer standaard alleen succesvolle, indexeerbare HTML-pagina's met een bruikbare
  canonical; functionele en discovery-only pagina's blijven buiten reguliere intentacties.
- Bewaar automatische classificatie en handmatige, optioneel gelockte overrides afzonderlijk.
- Presenteer mismatch, ontbrekende vervolgstappen, cannibalisatie en contenthiaten eerst als
  controle of kans, niet als automatisch hard probleem.
- Maak analytics provider-onafhankelijk en tel GA4- en Matomo-resultaten nooit stilzwijgend op.
- Gebruik AI later alleen voor semantische twijfelgevallen en adviestekst; deterministische
  signalen, GSC-bewijs en handmatige keuzes blijven zelfstandig bruikbaar.

Voorbereidend werk wordt bewust met aangrenzende roadmapitems uitgevoerd:

1. **Interne-linksemantiek:** bewaar of leid linkcontext af als hoofdcontent, CTA, navigatie,
   footer, breadcrumb of gerelateerde content. Dit is zowel zelfstandig SEO-bewijs als noodzakelijke
   basis voor intentiedoorstroom.
2. **Matomo-integratie:** introduceer een kleine provider-onafhankelijke analyticslaag en neem,
   voor zover de bron dit betrouwbaar levert, transitions, events, doelen, conversies, downloads,
   uitgaande links en interne zoekopdrachten mee. Toon ook URL-koppelingsgraad en niet-gekoppelde
   varianten. Hierdoor hoeft fase 10 de Matomo-import niet opnieuw te ontwerpen.
3. **GSC en opportunity-engine:** behoud queryregels, pagina-totalen, branded-configuratie en
   dekking geschikt voor periodegebonden query-intentieverdelingen. De feitelijke
   queryclassificatie blijft onderdeel van fase 10.
4. **AI-advieslaag:** hergebruik later classificatieversies, inputhashes en confidence, maar maak
   fase 10 niet afhankelijk van een specifieke AI-provider.

Acceptatie voor de latere module:

- Iedere conclusie toont gebruikte bronnen, periode, confidence, dekking en zwaarst wegend bewijs.
- Waarschijnlijkheden vormen binnen afrondingsmarge samen 1 en worden niet opnieuw berekend wanneer
  inputhash en classificatieversie gelijk zijn.
- Een handmatige keuze blijft na crawls en heranalyses behouden totdat deze expliciet wordt gereset.
- Pagina's zonder voldoende content-, query- of analyticsbewijs leveren geen harde actie op.
- Meerdere URL's gelden alleen als intentieconcurrenten bij aantoonbare GSC-overlap of sterke
  inhoudelijke en structurele overeenkomst.
- Bezoekersroutes worden als geobserveerde samenhang gepresenteerd en nooit als causale attributie.

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

Status: geïmplementeerd, gedeployed en op 2026-07-30 met Schipper Kozijnen gevalideerd.
Een volledige crawl verwerkte 644 URL's zonder fouten en leverde 33 onderliggende records op,
tegenover 170 vóór de correctie. Functionele zoekpagina's en dynamische openingsteksten bleven stil;
11 gelijktijdige canonical-, schema- en interne-linkwisselingen werden als één websitebrede
domeinverwisseling gepresenteerd.

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
- Verwachte content-, link- en schemaverschuivingen op expliciet genummerde archiefpagina's niet
  als wijziging opslaan; technische, metadata- en indexatieveranderingen op die pagina's wel
  behouden.

### Taakgerichte aanbevelingen en eigenaarschap

Status: fundament, eerste REST-API en eenvoudige taakweergave technisch geïmplementeerd; deployment
volgt. De eerste versie bevat 15 versiebeheerde aanbevelingstypen, taakcreatie vanuit een issue,
duplicaatpreventie, tenantautorisatie, gecontroleerde statusovergangen, eigenaarschap, issue- en
URL-koppelingen, onveranderlijke events, klantgebonden feedback en gescheiden taak- en
verificatiestatussen. De issue-popup toont nu rol, tijdsindicatie, stappen, gereedcriteria en
taakbediening zonder de diagnosestatus te vermengen. Een zelfstandig taakoverzicht en
verificatiejobs volgen in afzonderlijke stappen. Uitvoeringsfeedback voor werkelijke tijd,
moeilijkheid, bruikbaarheid, ontbrekende input en eindbeoordeling wordt inmiddels klantgebonden
vastgelegd. De huidige `recommended_action`, begeleiding, toewijzing, vervaldatum, comments en
`activity_log` blijven de bestaande productbasis.

Doel en gebruikerswaarde:

- Maak iedere aanbeveling uitvoerbaar voor iemand die de onderliggende SEO-analyse niet zelf heeft
  gedaan.
- Beantwoord in de standaardtaak wat moet veranderen, waarom, door wie, met welke stappen,
  tijdsbandbreedte, afhankelijkheden, gereedcriteria en verificatiemethode.
- Houd crawlerbewijs, historische vergelijking, confidence, alternatieve verklaringen en
  databronnen beschikbaar in een aparte analyseweergave.

Gefaseerde scope:

1. **Aanbevelingsbibliotheek en gedeeld begrippenmodel**
   - Inventariseer bestaande issuetypen en groepeer ze in versieerbare aanbevelingstypen.
   - Leg per type standaardtitel, primaire en ondersteunende rollen, prioriteitsregels,
     tijdsbandbreedte, uitvoerbaarheidsniveau, benodigde input, stappen, gereedcriteria,
     verificatiescope en verificatieregels vast.
   - Ondersteun minimaal contentredacteur, UX/UI-designer, webdeveloper, SEO-specialist,
     analytics-specialist, websitebeheerder en projectmanager/beslisser.
   - Gebruik prioriteiten kritiek, hoog, normaal en laag met een tekstuele onderbouwing; geen
     onverklaarde totaalscore.
2. **Taak- en analyseweergave**
   - Toon standaard alleen taak, reden, eigenaar, prioriteit, indicatieve tijd, stappen,
     afhankelijkheden en gereedcriteria.
   - Toon technisch bewijs, meetperioden, gebruikte regels en hypotheses uitklapbaar.
   - Tijd blijft een bandbreedte met confidence en schaalt aantoonbaar met URL-aantal,
     templatebereik, CMS-kennis, benodigde input en technische complexiteit.
3. **Uitvoering en historie**
   - Registreer bij iedere taakstatuswijziging actor, vorige en nieuwe status, tijdstip,
     toelichting, aangepaste URL's en gekozen verificatie.
   - Ondersteun functioneel open, gepland, in uitvoering, wacht op input, uitgevoerd,
     controle ingepland/actief, waarschijnlijk opgelost, handmatige controle nodig, opgelost,
     niet opgelost en afgewezen.
   - Behoud detectiestatus, suppressions en automatische issue-lifecycle zonder betekenisverlies.
4. **Latere projectspecifieke instructies**
   - Voeg uitbreidbare instructieprofielen toe voor WordPress, headless CMS, Lovable, React,
     bekende templates en componenten.
   - Bouw de eerste versie niet afhankelijk van volledige CMS- of repositorykennis.
5. **Privacyveilige kalibratie uit productiefeedback**
   - Verzamel eerst klantgebonden uitvoeringstijd, bruikbaarheid, correcties, afwijsredenen en
     verificatie-uitkomsten. De eerste gestructureerde feedbackregistratie is geïmplementeerd;
     correcties, afwijzingen en technische verificatie worden verder uitgebreid wanneer de
     bijbehorende workflows beschikbaar zijn.
   - Bereken later uitsluitend anonieme aggregaten bij minimaal 10 onafhankelijke klanten en 50
     beoordeelde taken, met begrensde bijdrage per klant en onderdrukking van kleine cellen.
   - Gebruik aggregaten eerst voor effort-, confidence- en verificatiekalibratie; activeer geen
     zelflerende productieregel zonder offline evaluatie, expliciete goedkeuring en versiebeheer.
   - Deel nooit ruwe content, URL's, queries, analyticsregels, vrije opmerkingen of
     klantidentiteiten tussen tenants.

Niet in scope:

- Websitewijzigingen automatisch publiceren.
- AI zelfstandig ingrijpende acties laten besluiten, zoals verwijderen, samenvoegen, splitsen of
  noindex.
- Tijdinschattingen als garantie of algemene SEO-score presenteren.

Ontwerpbesluit vóór de eerste migratie:

- **Voorstel:** ontwerp aanbevelingstypen en taakworkflow samen met de bestaande issue-engine, maar
  voer ze apart uit. Gebruik issues als diagnosebron en voeg alleen wanneer nodig een gekoppelde
  taak-/uitvoeringslaag toe. Hiermee blijft de automatische `resolved`/`verified` lifecycle
  gescheiden van menselijke statussen zoals `uitgevoerd` en `wacht op input`.
- **Alternatief:** breid `issues.status` rechtstreeks uit. Dit vraagt minder tabellen, maar vermengt
  detectie, uitvoering en verificatie en vergroot het risico op foutieve heropening of verificatie.
- Beslismoment: na inventarisatie van aanbevelingstypen en statusovergangen, vóór datamodel en
  Alembic-migratie.

Acceptatie:

- Iedere taak heeft precies één primaire uitvoerdersrol en optioneel ondersteunende rollen.
- Een niet-specialist kan de taak uitvoeren zonder aanvullende SEO-uitleg te hoeven vragen.
- Iedere prioriteit en tijdsbandbreedte toont de gebruikte factoren en onzekerheid.
- Gereedcriteria zijn technisch of handmatig toetsbaar en sluiten aan op de verificatiemethode.
- Taak- en analyseweergave gebruiken hetzelfde bewijs zonder het te dupliceren.
- Bestaande issuehistorie, suppressions, bulkacties en automatische lifecycle blijven intact.
- Klantoverstijgende kalibratie blijft uitgeschakeld totdat privacygrondslag, minimale volumes en
  evaluatiecriteria zijn goedgekeurd.

### Gerichte verificatiecrawls na uitvoering

Status: verificatiemodel, read-only scopeplan, dedicated executor en de eerste verificatieregels
zijn geïmplementeerd, gedeployed en op 2 augustus 2026 operationeel gevalideerd.
`repair_broken_internal_link`, `fix_redirect_chain_or_loop` en
`correct_canonical` controleren gericht bron en noodzakelijke doelen. Redirect- en canonicaldoelen
worden ook op bereikbaarheid, indexeerbaarheid en onverwachte canonicals beoordeeld. Het scopeplan
blokkeert een verzoek zolang
de taak niet uitgevoerd is of vereiste bron-, doel-, oude-, nieuwe- of canonicalrollen ontbreken.
De bestaande Redis/RQ-infrastructuur, crawlbeveiliging, snapshots, hashes en lichte crawlqueue
worden hergebruikt, maar de algemene `light_check` wordt niet direct gebruikt omdat die standaard
alle actieve website-URL's verwerkt.
Een gerichte controle start nooit impliciet een volledige websitecrawl.

De executor ondersteunt daarnaast al interne links naar redirects, ontbrekende pagina's,
indexatiecorrecties, titles, primaire H1-koppen, meta descriptions en structured data. Precieze
classificatie van een link als hoofdcontent, navigatie, footer of CTA volgt pas nadat
interne-linksemantiek die context betrouwbaar in het linkmodel bewaart.

Doel en gebruikerswaarde:

- Controleer snel of een gemelde aanpassing live en technisch correct is door alleen noodzakelijke
  URL's te crawlen.
- Laat de gebruiker ondertussen andere taken openen en uitvoeren; de controle overleeft navigatie,
  gesloten modals en beëindigde browsersessies.

Scope:

1. De gebruiker markeert een taak als uitgevoerd, registreert aangepaste URL's en kiest of bevestigt
   de voorgestelde verificatiescope.
2. De aanbevelingsbibliotheek bepaalt de vereiste URL-rollen en vult ze waar mogelijk uit
   issuebewijs, linkgraaf en snapshots; een bevoegde gebruiker corrigeert alleen ontbrekende of
   onjuiste rollen binnen de websitescope.
3. Een idempotente achtergrondjob bewaart queued/running/partially_completed/completed/failed/
   cancelled, retries, betekenisvolle voortgangsstappen en foutdetails.
4. De crawler bewaart voor- en nasnapshot, gecontroleerde regels en uitkomst: opgelost,
   waarschijnlijk opgelost, gedeeltelijk opgelost, niet opgelost of handmatige controle nodig.
5. De UI toont een globale, niet-blokkerende status, bijvoorbeeld `2 controles actief`, plus
   stappen als URL ophalen, analyseren, doel controleren, vergelijken en resultaat opslaan.
6. Na afronding wordt een melding in de applicatie en een auditregel aangemaakt; externe meldingen
   blijven een latere uitbreiding.

Verificatiescope:

- Title, description, heading, content of schema op één pagina: aangepaste URL.
- Interne link: bron- en doel-URL.
- Redirect: oude en nieuwe URL.
- Canonical: bron, canonical-doel en alleen noodzakelijke variant.
- Template, navigatie of footer: representatieve steekproef of gerichte impactcrawl.
- Robots, migratie of aantoonbaar sitebrede wijziging: technische sitecontrole of volledige crawl.

Productgrenzen:

- `Websitewijziging gecontroleerd` betekent alleen dat de eigen crawler de wijziging live ziet.
- `Google-verwerking nog niet vast te stellen` blijft apart totdat Google-signalen beschikbaar zijn.
- `Effectmeting nog niet beschikbaar` blijft apart totdat voldoende GSC- of analyticsdata bestaat.
- Inhoudelijke, juridische, visuele of tone-of-voicekwaliteit kan na technische controle
  `waarschijnlijk opgelost — handmatige controle nodig` blijven.

Afhankelijkheden:

- Hard: betrouwbare URL-normalisatie, snapshots/hashes, crawlqueue, issuebewijs,
  aanbevelingstypen en tenantautorisatie.
- Aanbevolen: taak-/activiteitshistorie en in-app notificatiemodel.
- Kan parallel: uitbreiding van interne-linksemantiek en elementlocaties voor preciezere checks.
- Geen harde afhankelijkheid: Matomo, zoekintentie, AI of gedeelde batchverwerking voor volledige
  sitecrawls.

Acceptatie:

- Een wijziging op één pagina start geen volledige crawl.
- Automatisch afgeleide en handmatig gecorrigeerde URL-rollen zijn tenantveilig en auditbaar.
- De job blijft actief buiten de pagina en browsersessie en blokkeert ander werk niet.
- Scope, voor- en nasituatie, uitgevoerde regels en conclusie zijn aan dezelfde taak gekoppeld.
- Interne-linkverificatie controleert bron, crawlbare hoofdcontentlink, anker, doelstatus,
  indexeerbaarheid en onverwachte canonical.
- Redirectverificatie controleert status, directe bestemming, keten/loop, eindstatus en canonical.
- Onzekere of gedeeltelijke uitkomsten vragen handmatige controle en worden niet automatisch
  `opgelost`.
- Een verificatieclaim zegt nooit dat Google de wijziging al heeft geïndexeerd.

### Periodieke volledige crawls naast gerichte controles

Status: bestaand gedrag behouden en na introductie van verificatiecrawls expliciet bewaken.

- De scheduler plant volledige sitecrawls standaard wekelijks; website-instellingen worden later
  de leidende configureerbare bron voor dagelijks, wekelijks, tweewekelijks, maandelijks of
  handmatig.
- Volledige crawls blijven nodig voor nieuwe en verdwenen URL's, externe wijzigingen,
  sitebrede regressies, interne-linkstructuur, templates en problemen buiten actieve taken.
- Gerichte verificaties mogen de verschuldigdheid van een volledige crawl niet verversen.
- Een volgende volledige crawl mag een eerdere gerichte uitkomst in bredere context bevestigen of
  heropenen zonder dubbele taak aan te maken.

Acceptatie:

- De standaard blijft één volledige crawl per zeven dagen.
- Een gerichte verificatie verschuift de geplande volledige crawl niet.
- Nieuwe problemen buiten de verificatiescope worden bij de volgende volledige crawl normaal
  ontdekt.

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

### Fase 8B — Gedeelde batchverwerking binnen één websitecrawl

Status: gepland na productievalidatie van asset- en mediakwaliteit en een nulmeting van crawlduur,
NAS-belasting en databasebelasting.

Doel: idle crawlworkers laten bijspringen bij een lopende grote sitecrawl, zonder de website
onbegrensd te belasten of crawlresultaten minder betrouwbaar te maken.

#### Ontwerp

- Behoud één `crawl_job` en één `crawl_run` als coördinator en gezamenlijke resultaatcontainer.
- Splits de URL-frontier op in claimbare batches van standaard 50 URL's.
- Laat iedere beschikbare full-crawlworker atomair één batch claimen.
- Bewaar per batch status, eigenaar, heartbeat, poging, starttijd, eindtijd en foutmelding.
- Geef een batch automatisch opnieuw vrij wanneer de workerheartbeat verloopt.
- Voorkom dubbele URL-verwerking met een unieke claim per crawlrun en URL.
- Voeg nieuw ontdekte interne URL's veilig aan dezelfde frontier toe.
- Start sitebrede analyses en issue-reconciliatie pas wanneer alle batches definitief klaar zijn.
- Laat pauzeren, stoppen en de deployment-drain alle actieve batches coöperatief afbreken.
- Hervat alleen onafgeronde of verlaten batches; reeds opgeslagen snapshots blijven behouden.

#### Capaciteitsbeleid

- Start met drie crawlworkers als veilige standaard voor grote websites.
- Gebruik maximaal drie gelijktijdige batches voor één website.
- Pas `concurrency` en `request_delay_ms` toe als gezamenlijke domeinlimiet, niet afzonderlijk
  per worker.
- Houd één globale limiet aan voor actieve batches over alle websites en verdeel capaciteit eerlijk
  over klanten.
- Laat light checks voorrang of gereserveerde capaciteit behouden, zodat een volledige crawl kleine
  controles niet blokkeert.
- Maak een vierde worker optioneel en activeer deze pas wanneer productiemetingen voldoende vrije
  CPU, geheugen, databaseverbindingen en netwerkcapaciteit aantonen.

#### Verwachte opbrengst

- Drie workers leveren bij grotere crawls naar verwachting circa 1,8–2,4 keer versnelling.
- Trage URL's blokkeren niet langer de volledige frontier.
- Alleen een mislukte batch hoeft opnieuw te worden uitgevoerd.
- Voortgang, vastgelopen werk en resterende tijd worden nauwkeuriger meetbaar.
- Beschikbare capaciteit kan eerlijker over grote en kleine websites worden verdeeld.

#### Belangrijkste risico's en beheersing

- Overbelasting of 429-responses: centrale domeinlimiet, adaptieve vertraging en backoff.
- Dubbele snapshots of links: atomische databaseclaims en unieke constraints.
- Databasecontentie: begrensde batches, bulkbewerkingen en gemeten connection-poollimieten.
- Onjuiste crawldiepte: kortste bekende afstand transactioneel bijwerken en na afloop controleren.
- Voortijdige siteanalyse: expliciete coördinatorstatus en controle op ontbrekende actieve batches.
- Verloren batches na workeruitval: heartbeat, claim-time-out en idempotente herverwerking.
- Oneerlijke capaciteitsverdeling: round-robinplanning tussen websites en een limiet per website.

#### Gefaseerde uitrol

1. Meet de huidige crawl met één full-crawlworker: URL's per minuut, totale duur, analysetijd,
   CPU, geheugen, databaseverbindingen, fouten en 429-responses.
2. Implementeer batchmodel, claims, heartbeat en hervatten met twee workers; valideer dezelfde
   snapshots, links, crawldiepte en issues als bij enkelvoudige verwerking.
3. Activeer drie workers en stel batchgrootte en domeinlimiet af op productiegegevens.
4. Test een vierde worker alleen als capaciteitsproef; maak deze pas standaard wanneer de extra
   snelheidswinst opweegt tegen de hogere belasting.

Acceptatie:

- Twee of drie workers verwerken aantoonbaar verschillende batches van dezelfde crawlrun.
- Geen URL krijgt binnen één crawlrun meer dan één definitieve snapshot.
- Resultaten voor links, crawldiepte, wijzigingen en issues zijn inhoudelijk gelijk aan een
  enkelvoudige referentiecrawl.
- Een uitgevallen worker laat zijn batch na de claim-time-out veilig door een andere worker
  overnemen.
- Pauzeren, stoppen, deployment-drain en hervatten werken voor alle batches van dezelfde crawl.
- De gezamenlijke domeinlimiet en globale NAS-capaciteitslimiet worden nooit overschreden.
- De UI toont actieve workers, batches, verwerkingssnelheid en een realistische resterende tijd.
- Drie workers verkorten een representatieve crawl zonder significante stijging van time-outs,
  429-responses, 5xx-responses of databasefouten.

## Fase 9 — Matomo-integratie

Status: gepland als standaard analyticskoppeling naast GA4. De Bing Webmaster Tools-integratie is
hervat en gevalideerd, waardoor Matomo inhoudelijk ingepland kan worden zodra de huidige
stabiliteits- en issuekwaliteitspakketten zijn afgerond.

- Een Matomo-site koppelen via server-URL, `idSite` en een API-token met leestoegang.
- API-tokens versleuteld bewaren en uitsluitend via POST versturen, nooit in URL's of logs.
- Bezoeken, paginaweergaven, landingspagina's, verkeersbronnen, doelen en conversies importeren.
- Introduceer een kleine provider-onafhankelijke analyticslaag voor landingspagina's, events,
  conversies en beschikbare paginatransities; bestaande GA4- en nieuwe Matomo-imports blijven
  herkenbare adapters met eigen brondefinities.
- Importeer waar beschikbaar ook transitions, downloads, uitgaande links en interne zoekopdrachten,
  met expliciete dekking wanneer de Matomo-configuratie deze gegevens niet levert.
- Matomo-pagina's via genormaliseerde URL's aan het blijvende URL-register koppelen.
- Toon per website de URL-koppelingsgraad en niet-gekoppelde URL-varianten zonder functionele
  queryparameters automatisch te verwijderen.
- Issues en wijzigingen verrijken met verkeers- en conversie-impact, gelijkwaardig aan GA4-data.
- Matomo naast GA4 ondersteunen; geen van beide integraties verplicht maken.
- Per website een primaire analyticsbron voor opportunity-prioritering kiezen en cijfers van GA4
  en Matomo nooit stilzwijgend optellen.

Acceptatie:

- Een gebruiker kan een Matomo-verbinding testen en vervolgens de juiste site selecteren.
- Alleen gegevens van de gekoppelde Matomo-site worden opgeslagen en getoond.
- Verkeers- en conversiedata zijn per URL en vergelijkingsperiode beschikbaar.
- De analysemodule kan dezelfde providerinterface gebruiken zonder Matomo-specifieke responses te
  kennen; ontbrekende transition- of eventdekking blijft zichtbaar als onbekend.
- Een ongeldig of ingetrokken token veroorzaakt een duidelijke fout zonder geheimen te loggen.

## Fase 10 — Zoekintentie & klantreis

Status: toekomstig; start pas nadat fase 9 is gedeployed en de Matomo-koppeling en
provider-onafhankelijke analyticslaag in productie zijn gevalideerd.

Uitvoeringsvolgorde:

1. Leg taxonomie, versieerbaar bewijsmodel, branded termen, sectorsjablonen en handmatige overrides
   vast via Alembic en bestaande website-/URL-identiteiten.
2. Classificeer pagina-inhoud en GSC-query's hybride en uitlegbaar; cache queryclassificatie per
   query, taal en markt en bewaar verdelingen op basis van vertoningen en klikken met dekking.
3. Voeg website-, cluster- en paginaverdelingen toe, plus intentiemismatch, interne doorstroom,
   cannibalisatie en concrete contenthiaten op basis van voldoende bewijs.
4. Koppel de primaire analyticsbron voor landingsgedrag, flexibele klantreisroutes, uitval,
   microconversies en primaire conversies zonder causaliteit te claimen.
5. Voeg een compacte interface toe met Overzicht, Pagina's, Clusters, Doorstroom, Kansen en
   Instellingen. Gebruik de bestaande navigatie, tabellen, filters en actielifecycle.
6. Laat de data-gedreven opportunity-engine concrete acties prioriteren als hoog, gemiddeld, laag
   of onvoldoende bewijs; voer samenvoegen, splitsen, noindex of publicatie nooit automatisch uit.

De module bewaart classificatiehistorie, inputhash, model-/prompt-/formuleversie, confidence,
signalen en analyseperiode. Query- en analyticsdata blijven in hun bestaande brontabellen en worden
niet gedupliceerd. SERP-intentie blijft een latere provideruitbreiding tenzij dan al een betrouwbare
SERP-bron beschikbaar is.

### Effectmeting na uitgevoerde aanbevelingen

Status: latere uitbreiding nadat taakstatussen, verificatiesnapshots, stabiele GSC- en
Matomo-imports en voldoende historie beschikbaar zijn.

- Vergelijk gelijkwaardige perioden vóór en na uitvoering met minimale datadrempels voor
  vertoningen, klikken, CTR, positie, landingsbezoeken, doorstroom, events, doelen en conversies.
- Houd implementatiecontrole, mogelijke Google-verwerking en waargenomen prestatieontwikkeling als
  drie afzonderlijke conclusies.
- Corrigeer of waarschuw voor positieverschil, seizoen, weekdagen, campagnes, branded verkeer,
  meetdekking en andere gelijktijdige wijzigingen.
- Gebruik voorzichtige formuleringen en claim geen causaliteit.
- Koppel meetresultaten aan de taakgeschiedenis en opportunity-engine zonder oorspronkelijke
  issues, snapshots of bronmetrics te dupliceren.

Acceptatie:

- Een effectvergelijking toont perioden, datadekking, relevante verschillen en onzekerheden.
- Onvoldoende of onvergelijkbare data levert `effect nog niet vast te stellen`, niet nul effect.
- De tool zegt nooit dat een taak een prestatieverandering heeft veroorzaakt.
- De gebruiker kan implementatie, Google-verwerking en effect als afzonderlijke stadia volgen.

Beslismomenten voor latere bundeling:

- Ontwerp effectmeting samen met de opportunity-engine en zoekintentie/klantreis, maar release deze
  apart nadat Matomo stabiel is; samen uitvoeren zou fase 10 onnodig vergroten.
- Ontwerp externe taakmanagementkoppelingen en externe notificaties pas wanneer de interne
  taakworkflow in productie is gevalideerd; vroegtijdig bouwen maakt externe systemen leidend voor
  een nog veranderend statusmodel.

## Deploymentafspraak

Releases worden als Git-archive naar `/tmp/seotool-<commit>-r<nummer>.tar.gz` geschreven. Upload naar
de NAS gebeurt via SSH-streaming met `dd`. Controleer op de NAS altijd eerst SHA-256, pak daarna uit
met `sudo tar --no-same-owner` en bouw en herstart alleen geraakte services. Migrations worden alleen
uitgevoerd wanneer een nieuw Alembic-bestand onderdeel van de release is.

## Afzonderlijke NAS-stagingomgeving

Status: volledig geïnstalleerd en gevalideerd op de NAS.

- Gebruik een zelfstandige `compose.staging.yaml` en projectnaam `seo-monitor-staging`; hergebruik
  geen productiecontainers, netwerken, volumes, database of secrets.
- Start standaard alleen API, PostgreSQL en Redis. Scheduler, crawlers, integratie- en
  exportworkers ontbreken uit de stagingstack en kunnen dus niet per ongeluk starten.
- Publiceer de staging-API uitsluitend op NAS-loopback en benader haar vanaf de Mac via een
  lokale SSH-tunnel; DSM Reverse Proxy en firewallwijzigingen zijn voor de eerste versie niet nodig.
- Geef staging via `cpu_shares` een lagere relatieve CPU-prioriteit dan productie en begrens het
  gezamenlijke geheugen tot maximaal 4 GB. De Synology-kernel ondersteunt geen harde Docker
  `NanoCPUs`- of PIDs-limiet. Voer builds en volledige tests bewust uit wanneer productie rustig is;
  builds hebben afzonderlijke piekbelasting.
- Gebruik eigen stagingsecrets en synthetische testdata. Kopieer geen productiedatabase naar
  staging.
- Beheer staging via de bestaande interactieve NAS-shell. Gebruik Container Manager alleen voor
  read-only statuscontrole wanneer dat werkelijk helpt.

Acceptatie:

- Productie en staging delen geen benoemde volumes, Compose-projectnaam of secretsbestand.
- Staging is niet rechtstreeks vanaf LAN of internet bereikbaar.
- Geen stagingservice kan automatisch crawls, exports of integraties starten.
- Stoppen of verwijderen van staging raakt geen productiecontainer of productievolume.
- CPU-, geheugen- en schijfbelasting worden vóór en tijdens een testbuild gemeten.

De configuratie blijft overdraagbaar naar een latere VPS-productieomgeving. Productiecomponenten
worden daarbij niet over NAS en VPS verdeeld: de VPS krijgt de volledige publieke productiestack;
de NAS blijft staging-, back-up- en herstelplatform. Het beoogde toekomstige domein is
`thactual.nl`; dit wordt pas bij die migratie technisch geconfigureerd.

## Databaseonderhoud na retentionpilot

Status: afgerond en op 1 augustus 2026 in productie gecontroleerd.

- Migratie `0034` activeert eerder vacuüm en analyse voor `element_locations` in staging en
  productie.
- In totaal zijn `6.787.671` oude, probleemvrije elementlocaties verwijderd; `2.729.964` beschermde
  locaties resteren.
- De eindaudit rapporteerde nul kandidaten voor vier websites en nog `4.431` voor Floris en Van
  Maurik; die laatste kandidaten zijn daarna in één begrensde batch verwijderd.
- Vóór die laatste kleine batch rapporteerde PostgreSQL nul geschatte dode rijen en recente
  automatische vacuüm- en analysestatistieken; een handmatige `ANALYZE` was niet nodig.
- Herhaal een onderbroken verwijdercommando nooit zonder eerst read-only na te tellen.
- Ontwerp GSC-retentie afzonderlijk; verwijder nog geen historische GSC-rijen.

Acceptatie:

- Staging en productie rapporteren migratie `0034` en de vier verwachte tabelopties: behaald.
- Beschermde elementlocaties zijn behouden en productie is gezond: behaald.
- Maintenance is afgesloten met `active=false safe=false tracked=0 waiting=0`: behaald.

## Automatische retentie en databasegroeibewaking

Status: afgerond, gedeployed en op 1 augustus 2026 in productie gevalideerd; 322 tests geslaagd.

- Start begrensde elementlocatie-retentie per website na een geslaagde volledige crawl.
- Selecteer websites automatisch; gebruik geen handmatig gekopieerde website-ID's.
- Bewaar onderhoudsoperaties, batches, voortgang en fouten persistent in PostgreSQL.
- Maak hervatten na terminal-, proces- of workeronderbreking idempotent.
- Bescherm actieve crawls, de nieuwste relevante crawls en snapshots, en issuebewijs volgens de
  bestaande retentionaudit.
- Voeg een hervatbaar onderhoudscommando voor alle websites, periodieke audits, structured logging
  en groeialarmen toe.
- Houd GSC- en interne-linkretentie als afzonderlijke beleidsbesluiten.

Acceptatie:

- Migratie `0035`, API en alle geraakte workers zijn gezond op staging en productie: behaald.
- Vijf persistente productieoperaties zijn zonder fout afgerond: behaald.
- Eén operatie bereikte eerst de limiet van 50.000 rijen en hervatte daarna automatisch via de
  scheduler tot `succeeded`: behaald.
- In totaal zijn tijdens deze productievalidatie 185.741 oude, onbeschermde elementlocaties in 19
  batches verwijderd; vier andere websites hadden nul kandidaten.
- Gelijktijdige crawl- en cleanupmutaties voor dezelfde website zijn via een persistente
  `waiting_for_crawl`-toestand uitgesloten en door regressietests afgedekt.
- Nieuwe volledige crawls maken voortaan automatisch een eigen idempotente retentieoperatie.

## Publieke website-inschatting en pakketadvies

Status: veilige read-only backend technisch geïmplementeerd; publieke interface, stagingdeployment
en productievalidatie volgen.

- Laat een bezoeker een website-URL invullen en lees veilig `robots.txt` en sitemaps.
- Normaliseer en ontdubbel URL's en beperk discovery tot het publieke domein.
- Gebruik zonder sitemap uitsluitend een begrensde steekproefcrawl.
- Toon vóór eigendomsverificatie alleen geschat volume en pakketadvies, geen technische problemen.
- Bepaal het definitieve volume na registratie, verificatie en een volledige crawl.
- Tel actieve, relevante canonical HTML-pagina's en sluit assets, externe URL's,
  trackingvarianten en filterexplosies uit.
- Baseer pakketwissels op het gemiddelde van twee volledige crawls; verhoog nooit automatisch na
  één overschrijding.

Voorlopige pakketten:

- Klein: tot 100 pagina's, volledige crawl maandelijks, indicatief EUR 39 per maand.
- Groei: tot 1.000 pagina's, volledige crawl tweemaal per maand, indicatief EUR 79 per maand.
- Groot: tot 10.000 pagina's, volledige crawl wekelijks, indicatief vanaf EUR 149 per maand.
- Maatwerk: meer dan 10.000 pagina's of afwijkende frequentie, opslag en verwerking.
- Frequentere monitoring blijft een add-on en dwingt geen groter paginapakket af.

## Publieke vraagassistent en eerlijke doorverwijzing

Status: gepland na de publieke website-inschatting en vóór de definitieve homepageafronding. Dit
onderdeel staat op de roadmap, maar is niet automatisch een friends-and-family-releasegate zonder
een afzonderlijk expliciet scopebesluit.

- Voeg op de homepage een compacte zoekbalk toe voor natuurlijke vragen over SEO, crawling,
  content, monitoring, rapportage, AI-search en aanverwante onderwerpen.
- Gebruik een redactioneel beheerde, versieerbare kennisbank als feitelijke bron. Leg per intentie
  uitleg, doelgroep, beschikbare SEO Monitor-functies, beperkingen, roadmapstatus, alternatieven en
  laatste inhoudelijke controle vast.
- Begin zonder generatieve AI: normaliseer invoer, herken synoniemen en typefouten, weeg matches in
  vraag en onderwerp zwaarder dan losse verwante termen en toon een beperkt aantal relevante
  vervolgvragen.
- Gebruik AI later alleen optioneel voor intentieherkenning, verduidelijkingsvragen en natuurlijke
  formulering. AI mag geen productmogelijkheden, roadmapstatus, concurrenteigenschappen of
  actuele prijzen zelfstandig bedenken.
- Maak altijd zichtbaar of iets `nu beschikbaar`, `deels beschikbaar`, `gepland` of `niet door SEO
  Monitor ondersteund` is.
- Verwijs bij een duidelijke mismatch eerlijk naar een geschiktere toolcategorie en, wanneer
  redactioneel actueel gecontroleerd, naar concrete alternatieven. Toon commerciële relaties of
  affiliatebelangen expliciet.
- Geef wanneer SEO Monitor een behoefte niet of onvoldoende ondersteunt een expliciet negatief
  geschiktheidsantwoord en adviseer maximaal twee tools die voor die concrete behoefte aantoonbaar
  beter passen. Leg kort uit waarom deze kandidaten geschikter zijn; probeer de vraag niet alsnog
  naar een SEO Monitor-verkoopargument om te buigen.
- Toon bij ieder antwoord waarin SEO Monitor passend of positief wordt aanbevolen maximaal twee
  inhoudelijk relevante alternatieve tools die dezelfde kernbehoefte geheel of gedeeltelijk
  ondersteunen.
- Benoem per alternatief zowel waar die tool aantoonbaar sterk in is als de verifieerbare
  verschillen met SEO Monitor. Gebruik nooit een onbewezen claim dat een concurrent iets niet kan;
  schrijf bij ontbrekend bewijs dat de functie niet in de gecontroleerde openbare
  productinformatie is aangetroffen.
- Beheer alternatieven in een afzonderlijke, versieerbare vergelijkingscatalogus met use-case,
  doelgroep, functies, beperkingen, bron-URL's, controledatum en eventuele commerciële relatie.
  Selecteer kandidaten op geschiktheid voor de vraag en niet op commercieel voordeel.
- Gebruik [Saijo George's Best Marketing Tools](https://saijogeorge.com/best-marketing-tools/) als
  brede, handmatig samengestelde ontdekkingsbron voor categorieën en kandidaattools. Behandel deze
  lijst niet als zelfstandig bewijs: verifieer bestaan, actuele positionering, functies en
  beperkingen vóór publicatie altijd bij de officiële productbron van iedere kandidaat.
- Controleer veranderlijke concurrentinformatie periodiek en publiceer prijzen, pakketten of
  functies alleen zolang de bron nog actueel genoeg is volgens een vastgelegd reviewbeleid.
- Stel bij lage herkenningszekerheid één verduidelijkingsvraag of meld dat er onvoldoende basis is
  voor een betrouwbaar antwoord; geef nooit schijnzekerheid om toch volledig te lijken.
- Maak belangrijke antwoorden ook als gewone indexeerbare content beschikbaar. Een uitsluitend
  client-side zoekvenster geldt niet als vervanging voor inhoudelijke landings- of uitlegpagina's.
- Gebruik geanonimiseerde zoek- en geen-resultaatstatistieken om kennishiaten te vinden; sla geen
  onnodige persoonsgegevens of volledige gevoelige vragen op.

Acceptatie:

- Een vraag over crawling legt correct uit wat SEO Monitor doet, voor wie dat relevant is, welke
  grenzen gelden en wanneer een specialistische crawler geschikter is.
- Een vraag buiten de productscope levert een eerlijke afbakening en bruikbaar alternatief op,
  zonder een roadmapfunctie als beschikbaar te presenteren.
- Wanneer SEO Monitor niet geschikt is, zegt het antwoord dit ondubbelzinnig en toont het maximaal
  twee op actuele officiële productinformatie gebaseerde betere kandidaten met motivatie.
- Ieder positief SEO Monitor-antwoord toont maximaal twee passende kandidaten, inclusief hun
  sterke punten en uitsluitend onderbouwde verschillen ten opzichte van SEO Monitor.
- Een verouderde, onbevestigde of niet meer bereikbare bron voorkomt dat de bijbehorende
  concurrentclaim als actueel feit wordt getoond.
- Ieder antwoord is terug te leiden naar beheerde kennisblokken met status en controledatum.
- Dezelfde vraag levert zonder AI dezelfde feitelijke kern op; optionele AI verandert alleen
  interpretatie of formulering en kan bij onzekerheid veilig terugvallen.
- De homepage toont maximaal vijf overzichtelijke resultaten en blijft snel, toegankelijk en
  bruikbaar op mobiel.

## In-product contextuele data-assistent

Status: gepland als afzonderlijk productonderdeel. Functioneel, inhoudelijk en in de interface
gescheiden houden van de publieke homepagevraagassistent.

- Laat ingelogde gebruikers vragen stellen over de gegevens die zij op dat moment binnen SEO
  Monitor zien, zoals een URL, snapshot, wijziging, issue, crawl, taak, export of integratiemeting.
- Baseer ieder antwoord uitsluitend op tenantbevoegde zichtbare data, opgeslagen technisch bewijs,
  meetperioden, productregels en bijbehorende interne uitleg. Maak duidelijk welke feiten gemeten
  zijn, welke interpretatie de applicatie geeft en waar bewijs ontbreekt.
- Gebruik de actuele schermcontext als expliciete scope, waaronder website, geselecteerde entiteit,
  filters en meetmoment. Laat de gebruiker verduidelijken wanneer meerdere zichtbare records of
  perioden mogelijk bedoeld worden.
- Beantwoord alleen inhoudelijke vragen over de zichtbare klantdata en de betekenis daarvan binnen
  SEO Monitor. De in-product assistent geeft geen algemene marktvergelijkingen, concurrentnamen,
  affiliateverwijzingen of aanbevelingen zoals dat een functie in een andere tool beschikbaar is.
- Gebruik geen antwoorden, kandidatenroutes of fallbackgedrag van de publieke
  vergelijkingscatalogus. Houd endpoints, antwoordtypen, prompts of regels, logging en
  gebruiksmetingen aantoonbaar gescheiden, ook wanneer onderliggende technische componenten worden
  hergebruikt.
- Start geen crawl, statuswijziging, taakactie, export of andere mutatie vanuit een antwoord zonder
  een afzonderlijke expliciete gebruikershandeling en de bestaande autorisatiecontroles.
- Antwoord bij onvoldoende of niet-zichtbaar bewijs dat de conclusie niet uit de beschikbare data
  kan worden afgeleid. Vul geen ontbrekende klantdata aan met algemene aannames.
- Vergelijk ontwikkelingen standaard met de direct voorafgaande gelijkwaardige periode, dezelfde
  kalenderperiode één jaar eerder en, wanneer de dekking en definities vergelijkbaar zijn, dezelfde
  periode twee jaar eerder. Toon ontbrekende historie als onbekend en niet als nul.
- Gebruik gelijke aantallen kalenderdagen en benoem afwijkingen door seizoen, weekdagen, campagnes,
  consent, attributie, gewijzigde doelen of meetimplementaties. Vergelijk onverenigbare
  metricdefinities niet stilzwijgend.
- Ontleed leads minimaal naar kanaal, organische landingspagina, paginatype en conversieratio.
  Benoem welke pagina's de absolute stijging of daling het meest dreven en onderscheid extra
  verkeer van een gewijzigde conversieratio.
- Koppel GSC-klikken en vertoningen, analytics-landingssessies en conversies, crawlwijzigingen,
  issues en uitgevoerde taken via genormaliseerde URL en periode. Houd brondefinities en
  niet-gekoppelde data zichtbaar en tel GSC-klikken nooit op bij analytics-sessies.
- Genereer bij groei behoud- en uitbreidingsadviezen voor aantoonbare positieve drijvers. Genereer
  bij daling gerichte herstel- of onderzoekstappen voor de grootste negatieve paginabijdragen,
  verlies van relevante zichtbaarheid, lagere conversieratio, technische regressies of
  meetproblemen. Iedere aanbeveling noemt bewijs, onzekerheid, eigenaar en controle na uitvoering.
- Presenteer samenhang en waarschijnlijke verklaringen met confidence, maar claim geen causaliteit
  zonder passend experimenteel of ander sterk bewijs. Hergebruik hiervoor de geplande
  opportunity-engine en effectmeting in plaats van een tweede score- of conclusiemodel te bouwen.

### Analytics-meetkwaliteit en anomaliedetectie

Status: gepland als verplichte kwaliteitslaag vóór conversie-inzichten en aanbevelingen.

- Detecteer onwaarschijnlijke combinaties van gekwalificeerde events en sessies per dag,
  landingspagina en eventtype. Gebruik geen universele harde conversiegrens, maar combineer
  eventvolume, sessievolume, historische bandbreedte, plotselinge pieken en vergelijkbare pagina's.
- Signaleer herhaald afgevuurde events, abrupte eventpieken, events op bedank- of vervolgpagina's,
  token- en campagnevarianten, ontbrekende sessies en landingspagina's die niet logisch als ingang
  bij het event passen.
- Normaliseer alleen veilige URL-varianten voor analyse en behoud de oorspronkelijke bronregel als
  bewijs. Toon gevoelige querywaarden of tokens nooit in antwoorden, logging of exports.
- Verwijder of corrigeer verdachte events niet automatisch. Markeer ze als mogelijke
  meetafwijking, toon zowel ruwe als gevoeligheidsberekende totalen en verlaag de confidence van
  alle afhankelijke conversie-inzichten.
- Maak van een voldoende sterke afwijking één gededupliceerde analytics-kwaliteitscontrole met
  eventnaam, datum, geanonimiseerde of genormaliseerde pagina, events, sessies, historische
  vergelijking, waarschijnlijke meetoorzaken en concrete verificatiestappen voor analytics- of
  websitebeheer.
- Laat een meetkwaliteitscontrole na volgende imports de normale issue-lifecycle doorlopen en pas
  afhankelijke inzichten weer als betrouwbaar presenteren nadat de afwijking aantoonbaar wegblijft.
- Praktijkgeval Schipper Kozijnen: twintig nieuwsbrief-events op één dag, toegeschreven aan een
  regionale landingspagina met twee sessies, moet als waarschijnlijk meetprobleem worden herkend en
  mag niet stilzwijgend de conclusie `meer leads door hogere conversie` bepalen.

Acceptatie:

- Een vraag vanuit een issuedetail legt het zichtbare signaal, bewijs, relevantie, aanbevolen actie
  en verificatie uit zonder gegevens van andere klanten of schermcontexten te gebruiken.
- Een vraag over een waarde, status of verandering noemt het gebruikte meetmoment en kan naar de
  betrokken zichtbare bronrecords verwijzen.
- Een vraag over stijgende of dalende leads vergelijkt minimaal de vorige gelijkwaardige periode
  en, bij voldoende dekking, dezelfde periode één en twee jaar eerder.
- Het antwoord rangschikt de pagina's die de leadverandering het sterkst dreven en laat per pagina
  zien of verkeer, conversieratio of beide veranderden.
- Bij minder leads bevat het antwoord uitsluitend bewijsgebonden acties voor de belangrijkste
  negatieve drijvers en benoemt het expliciet wanneer eerst tracking of datadekking moet worden
  hersteld.
- Bij meer leads benoemt het antwoord welke positieve patronen behouden of verantwoord uitgebreid
  kunnen worden zonder de stijging automatisch aan één wijziging toe te schrijven.
- Een sterke event-/sessieafwijking maakt vóór de conversieconclusie zichtbaar dat de meting
  waarschijnlijk onbetrouwbaar is en toont het resultaat met en zonder de verdachte bijdrage.
- Een analytics-anomalie wordt niet automatisch verwijderd, maar blijft met bronbewijs,
  controledatum, status en verificatiehistorie beschikbaar.
- De in-product assistent noemt of adviseert geen externe tools, ook niet wanneer SEO Monitor een
  gevraagde functie niet ondersteunt.
- Een algemene SEO- of toolvergelijkingsvraag binnen het product wordt niet via de publieke
  antwoordroute afgehandeld; de gebruiker krijgt een korte scopeverklaring.
- Autorisatie-, tenantisolatie- en geen-onbedoelde-mutatieregels zijn met regressietests afgedekt.

## Invitation-only onboardingworkflow

Status: gepland; nog niet in uitvoering. Dit is een verplichte, releaseblokkerende fase vóór de
friends-and-family-release. De functionele scope, beveiligingskeuze, testmatrix en raming staan in
`docs/onboarding-friends-family.md`.

- Bouw voort op de bestaande accounts, uitnodigingen, rollen en atomaire klant-/websitecreatie.
- Voeg een begeleide en hervatbare flow toe van uitnodiging tot eerste crawlresultaten.
- Voeg één veilige methode voor website-eigendomsverificatie toe.
- Maak analytics-meetkwaliteit onderdeel van onboarding zodra een analyticsbron wordt gekoppeld:
  valideer koppeling en scope, leg gekwalificeerde leadevents en hun ingangsdatum vast, voer een
  historische nulmeting uit en toon een blijvende betrouwbaarheidsstatus.
- Laat ontbrekende of nog niet gevalideerde analytics technische onboarding en crawling niet
  blokkeren, maar presenteer afhankelijke conversie-inzichten niet als betrouwbaar.
- Plan bij onvoldoende historie automatische hercontroles na 7, 14 en 30 dagen en maak sterke
  afwijkingen tot gededupliceerde analytics-kwaliteitscontroles met bewijs en lifecycle.
- Houd ruimte voor een latere aanvullende meetservice rond meetplan, tagging, consent en handmatige
  validatie; de automatische basiscontrole en eerlijke betrouwbaarheidsstatus blijven inbegrepen in
  het product.
- Voorkom dubbele websites en initiële crawls bij refresh, dubbel klikken of opnieuw proberen.
- Valideer de volledige flow met minimaal twee niet-technische proefgebruikers.
- Start deze implementatie pas als een afzonderlijke ontwikkelfase expliciet wordt gekozen.

## Pakketdefinitie, prijzen en gratis gebruikstermijn

Status: bewust uitgesteld tot de volledige bestaande roadmap gereed is en de
friends-and-family-readiness wordt beoordeeld. Werk dit niet eerder uit of publiceer het niet
gedeeltelijk op de homepage.

Vóór een friends-and-family-release:

- definieer per pakket het paginavolume, de crawlfrequentie, inbegrepen functies, ondersteuning en
  grenzen;
- bepaal en motiveer een gratis gebruikstermijn van twee of drie maanden;
- toon in één duidelijke tabel zowel de gratis termijn als de reguliere kosten daarna;
- bepaal of prijzen inclusief of exclusief btw worden gecommuniceerd en laat commerciële en
  juridische teksten controleren;
- leg vast wat na afloop gebeurt met toegang, crawls, data, exports en verwijdering;
- voorkom automatische betaalde omzetting zonder een expliciete keuze van de gebruiker;
- laat de publieke website-inschatting pas een pakket adviseren wanneer deze definities definitief
  zijn en op dezelfde bronconfiguratie berusten als de prijstabel.

De bestaande indicatieve bedragen en grenzen zijn werkmateriaal en mogen tot dit besluit niet als
definitief aanbod op de homepage verschijnen.

## Friends-and-family-release

Status: geblokkeerd totdat de volledige roadmapscope die op 1 augustus 2026 in commit `71d732a`
stond is afgerond, gedeployed en waar relevant operationeel gevalideerd, of een onderdeel door de
gebruiker expliciet uit die scope is verwijderd. Er geldt geen kalenderdatum voor de release.

### Ontwikkeltijdraming

Basis van de raming op 1 augustus 2026:

- De Git-historie loopt vanaf 10 juli 2026: 23 kalenderdagen en 21 dagen met commits.
- In die periode zijn 235 commits gemaakt en is een werkende productie- en stagingomgeving met
  322 geautomatiseerde tests bereikt.
- Commitvolume is geen urendeclaratie. Integraties, migraties, gebruikersproeven en operationele
  acceptatie verlopen langzamer en onregelmatiger dan de eerste technische bouwfase.

De eerdere raming van 28–44 actieve werkdagen gold alleen voor de toen geselecteerde minimale
releasegates en is geen geldige releasedatum meer. Omdat nu de volledige huidige roadmap eerst moet
worden voltooid, geldt als grove planningsorde:

- circa vier tot zeven maanden verdere ontwikkeling vanaf 1 augustus 2026;
- een eerste volledige readiness-audit indicatief tussen december 2026 en maart 2027;
- geen release zolang één bestaand roadmaponderdeel nog `gepland`, `toekomstig`, `in uitvoering`,
  alleen lokaal geïmplementeerd of nog niet operationeel gevalideerd is.

Dit is een voortschrijdende raming, geen toezegging. Herbereken haar na iedere afgeronde hoofdfase.
Nieuwe wensen die later aan de roadmap worden toegevoegd blokkeren de release alleen wanneer de
gebruiker ze expliciet onderdeel maakt van dezelfde friends-and-family-scope.

### Readinessbesluit door de gebruiker

- Codex stelt niet zelfstandig vast dat de release doorgaat.
- Zodra Codex op basis van een volledige roadmapaudit denkt dat het project ver genoeg is, vraagt
  Codex de gebruiker expliciet of die vindt dat de friends-and-family-release mag worden voorbereid.
- Die vraag bevat altijd afzonderlijk redenen vóór release, redenen tegen release, resterende
  risico's, test- en productie-evidence en een duidelijke eigen aanbeveling.
- De gebruiker neemt het definitieve go/no-go-besluit. Zonder expliciet `ja` blijft de release
  geblokkeerd.
- Na een positief algemeen go/no-go vraagt Codex afzonderlijk en letterlijk of de homepage
  definitief klaar is. Een eerder `ja` of algemene releasegoedkeuring telt niet als antwoord op
  deze homepagevraag.
- Start geen friends-and-family-deployment totdat de gebruiker ook de homepagevraag expliciet met
  `ja` heeft beantwoord. Nieuwe homepagewensen zetten deze goedkeuring terug naar onbevestigd.

Redenen vóór release omvatten minimaal: alle afgesproken roadmapitems aantoonbaar afgerond,
geslaagde volledige tests, gezonde staging en productie, geslaagde onboardingproeven, bewezen
multi-clientisolatie, herstelbare back-ups en voldoende gemeten capaciteit.

Redenen tegen release omvatten minimaal: openstaande roadmapstatussen, bekende datarisico's of
ernstige fouten, handmatige onboardingstappen, onvoldoende begrijpelijkheid, onbewezen restore of
rollback, ontbrekende monitoring, onvoldoende VPS-capaciteit of onduidelijke privacy- en
toegangsafhandeling.

Doel:

- Nodig aanvankelijk drie tot vijf bekende gebruikers of organisaties uit.
- Gebruik echte websites en normale gebruikersflows, maar nog zonder brede publieke verkoop.
- Verzamel gericht feedback over onboarding, begrijpelijkheid, taken, rapportage en betrouwbaarheid.
- Houd de proef vier tot acht weken besloten voordat een bredere release wordt overwogen.

### Beoogde development- en productieopstelling

- **MacBook:** primaire werkplek voor Codex, broncode, Git, reviews, SSH en releasegoedkeuring;
  geen zware builds, crawls of lokale productiedatabase.
- **Linux-worker-pc:** afzonderlijk infrastructuurproject voor builds, volledige tests, linting,
  migratie- en herstelproeven en begrensde crawlexperimenten; nooit een noodzakelijke schakel voor
  publieke productie.
- **Synology NAS:** geïsoleerde staging, centrale opslag, snapshots, versleutelde back-ups en
  hersteltests; na migratie geen langdurige publieke productie of zware crawling.
- **VPS:** volledige zelfstandige publieke productiestack met API, PostgreSQL, Redis, scheduler en
  workers; productie blijft functioneren wanneer MacBook, thuis-pc, NAS of thuisinternet uitvalt.
- **Releaseflow:** MacBook naar Git, zware kwaliteitscontrole op de Linux-worker, gecontroleerde
  release naar de VPS en afzonderlijke back-up en herstelcontrole op de NAS.

### Infrastructuurgates

- Richt de pc eerst als afzonderlijk headless Ubuntu Server-project in en meet builds, tests,
  crawls, geheugen, schijf en netwerk voordat de SEO-tool hem gebruikt.
- Migreer productie pas nadat de VPS minimaal een aantoonbaar passend opslag-, geheugen- en
  retentiebudget heeft. De huidige 80 GB SSD is onvoldoende als veilige groeicapaciteit voor de
  volledige productiestack; richtwaarde is minimaal 160 GB en bij voorkeur circa 250 GB NVMe.
- Houd de volledige productiestack op de VPS; plaats geen productieworkers of live database op de
  thuis-pc of NAS.
- Maak dagelijkse versleutelde databaseback-ups naar de NAS en behoud daarnaast minimaal één
  onafhankelijke offsite kopie.
- Valideer restore, rollback, monitoring, certificaatvernieuwing, schijfruimtewaarschuwingen en
  herstel na service- of VPS-herstart vóór uitnodigingen worden verstuurd.

### Productgates

- Alle geplande homepagewijzigingen zijn verwerkt, responsive en functioneel gecontroleerd en de
  gebruiker heeft vlak vóór deployment afzonderlijk bevestigd dat de homepage definitief klaar is.
- Multi-clientisolatie is met minimaal twee afzonderlijke klanten en rollen opnieuw gecontroleerd.
- De invitation-only onboarding volgt de vastgelegde flow en acceptatiematrix in
  `docs/onboarding-friends-family.md`; publieke zelfregistratie is nog geen releasevoorwaarde.
- De volledige onboardingworkflow is vóór de release functioneel afgerond: uitnodiging of
  registratie, persoonlijk account, organisatie en website aanmaken, website-eigendom verifiëren,
  crawlvoorkeuren bevestigen, eerste crawl starten en voortgang en eerste resultaten tonen.
- Onboarding kan zonder handmatige databasewijziging, terminalhandeling of beheerdercorrectie
  worden voltooid en biedt herstelbare foutmeldingen, opnieuw proberen en hervatten na uitloggen.
- Onboarding, crawlstatus, issues, taakafhandeling en exports zijn begrijpelijk zonder directe
  technische begeleiding en zijn met minimaal twee niet-technische proefgebruikers doorlopen.
- Scheduler, retries, retentie, deployment-drain en workerherstel functioneren aantoonbaar.
- Iedere deelnemer weet dat dit een besloten test is en waar feedback en incidenten worden gemeld.
- Er is een eenvoudige procedure voor toegang intrekken, data exporteren en testdata verwijderen.

De Linux-worker verhoogt ontwikkelsnelheid en betrouwbaarheid, maar is geen releaseafhankelijkheid:
een storing thuis mag de friends-and-family-productie niet onderbreken.

## Gerichte verificatiecrawls

Status: tien taaktypen gedeployed en technisch gecontroleerd in productie.

- Dedicated executor voor defecte interne links, redirectketens/-loops en canonicals.
- Persistente scope, regels, voor-/nasituatie, fouten, retries en conclusie.
- Eén actieve verificatie per aanbevelingstaak; alleen beschikbaar voor uitgevoerde taken met een
  complete en ondersteunde URL-scope.
- Geen discovery, sitebrede issueherberekening of wijziging van de full-crawlplanning.
- Ondersteunt aanvullend interne redirects, herstel/redirect van ontbrekende pagina's en
  indexatiecorrecties.
- Ondersteunt aanvullend titles, primaire H1-koppen, meta descriptions en structured data.

### Volgende gebundelde release — begrijpelijke taakworkflow

Status: eerste begrijpelijkheidsverbetering en beslisgerichte orphan-correctie gedeployed via
migratie `0033`; verdere vereenvoudiging voor niet-technische gebruikers blijft gepland.

- Toon bovenaan één duidelijke hoofdactie die past bij de huidige taakstatus.
- Vertaal interne statussen en verificatietermen naar korte, taakgerichte uitleg.
- Presenteer `Wat moet ik doen?`, `Wanneer is het klaar?` en `Controle` in die vaste volgorde.
- Verberg technische URL-rollen, scopeversies en regelbewijs standaard achter uitklapbare details.
- Leg bij een uitgeschakelde actie direct uit welke stap of invoer nog ontbreekt.
- Maak het verschil zichtbaar tussen werk gereedmelden, automatisch controleren en definitief
  afsluiten.
- Behoud de volledige technische informatie voor beheerders en probleemonderzoek.

Acceptatie:

- Een gebruiker kan zonder SEO- of systeemkennis bepalen wat de eerstvolgende actie is.
- De hoofdroute van open taak naar uitgevoerde en gecontroleerde taak past zonder zijwaarts scrollen
  op 390 px.
- Technische details verdringen de taakactie niet, maar blijven met één handeling bereikbaar.
- Bestaande statusovergangen, URL-scopebewerking en gerichte verificaties blijven functioneel.

Aanvullende correctie:

- Behandel `orphan_page` als bewezen structuursignaal, niet als bewezen linktekort.
- Vraag eerst of de pagina zelfstandig moet blijven bestaan.
- Toon daarna twee heldere routes: structureel opnemen of samenvoegen/redirecten en sitemap
  bijwerken.
- Houd `important_page_few_internal_links` als afzonderlijke aanbeveling voor pagina's die al in de
  interne structuur staan.
- Migreer alle actieve orphan-taken klantoverstijgend naar de nieuwe beslisgerichte definitie.

### Gebundelde interfaceverbetering uitvoeringstaken

Status: uitgevoerd en gedeployed als onderdeel van de gebundelde verificatie-interface.

- Beperk de globale dialoogstijl van `dl div` tot directe definitierijen. Geneste taakcomponenten
  krijgen nu onbedoeld bovenlijnen en verticale padding.
- Vervang de tekst `Voortgang` in het vaste nummerbadge door een kort stapnummer of een afzonderlijk
  sectielabel; de huidige tekst loopt over de kop `Taakstatus bijwerken`.
- Maak de taakheader compacter en groepeer status met de overige metadata, zodat de statusbadge niet
  los in de rechterbovenhoek zweeft.
- Verminder de verticale ruimte tussen header, aanpak, criteria en bediening zonder de scanbaarheid
  te verliezen.
- Maak statusformulier en knoppen rustiger: een disabled knop moet duidelijk inactief zijn,
  toelichting moet op één regel beginnen en labels en velden moeten consistent uitlijnen.
- Controleer de volledige taakkaart binnen het echte issuedialoogvenster op desktop en mobiel;
  geïsoleerde componentpreviews zijn niet voldoende vanwege overervende dialoogselectors.

Acceptatie:

- Geen onbedoelde scheidingslijnen of overlappende tekst in de taakkaart.
- Header, stappen, criteria, statusbediening en verificatie vormen één compacte visuele hiërarchie.
- Geen horizontale overflow op 390 px en geen afgesneden bediening in het desktopdialoogvenster.
- De verificatiestroom blijft functioneel en toegankelijk via toetsenbord en zichtbare focusstijlen.

## Fase 11 — Volwaardige visuele issue-inspectie

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

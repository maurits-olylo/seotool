# Architectuur

De API verwerkt klanten, websites en instellingen. SQLAlchemy-modellen vormen de enige toegang
tot PostgreSQL; schemawijzigingen lopen uitsluitend via Alembic. Redis/RQ scheidt crawltaken van
HTTP-verzoeken. De scheduler wordt in fase 5 verantwoordelijk voor periodieke jobs.

Alle database-ID's zijn UUID's en tijdstempels worden in UTC opgeslagen. Crawler-, snapshot-,
wijzigings- en issuecomponenten blijven onderling gescheiden.

## Authenticatie

De publieke productschil is zonder sessie toegankelijk. Interne teamleden gebruiken een persoonlijk
account met een scrypt-wachtwoordhash en een ondertekende, HTTP-only sessiecookie. Eén gedeeltelijk
unieke database-index begrenst de globale rol `superuser` tot één account. Verdere rollen en
klanttoewijzingen volgen via afzonderlijke memberships; klantaccounts zijn nog niet actief. De
API-key blijft apart beschikbaar voor technische integraties en scripts.

`client_memberships` koppelt interne gebruikers aan klanten met rol `admin`, `user` of later
`client`. De superuser en technische API-key hebben globale toegang. Een admin kan klanten aanmaken
en beheert alleen klanten waarvoor een admin-membership bestaat. Een user kan toegewezen data lezen,
issuestatussen bijwerken en exports gebruiken, maar geen integraties, instellingen of crawls beheren.
Deze rechten worden in API-routes afgedwongen; verborgen menu-items zijn alleen de UI-weergave ervan.
Iedere ingelogde rol kan de klantgebonden rapportages lezen. Client-accounts landen uitsluitend in
de rapportageomgeving; users, admins en de superuser kunnen dezelfde rapportage naast hun toegestane
operationele schermen openen. Website- en klantscoping blijft voor alle rollen door de API afgedwongen.

Interne gebruikers worden via een klantgebonden uitnodiging toegevoegd. De eenmalige token is alleen
als SHA-256-hash opgeslagen, verloopt na zeven dagen en levert bij acceptatie zowel het account als de
membership op. Admins kunnen alleen users uitnodigen; alleen de superuser kan admins uitnodigen.

## URL-discovery

`urls` bewaart één blijvende URL-identiteit per website; `url_sources` legt vast of een URL via
sitemap, interne link of een eerdere crawl bekend is. Normalisatie gebeurt vóór opslag. Een
verdwenen bron verwijdert het URL-record niet. `crawl_jobs` vormt de persistente basis voor werk
dat vanaf fase 3 door de worker wordt uitgevoerd.

## Crawlproces

De HTTP-laag valideert elke URL en redirect tegen SSRF, begrenst redirects, time-outs en
responsegrootte. HTML-extractie levert afzonderlijke hashes voor HTML, hoofdcontent, metadata,
links en structured data. Iedere meting wordt opgeslagen als `url_snapshot`; links horen bij de
betreffende `crawl_run`, terwijl `urls` alleen de actuele samenvatting en blijvende identiteit houdt.
Pauze- en stopverzoeken worden niet alleen tussen URL-verzoeken verwerkt, maar ook tijdens lange
sitebrede analyses na de laatste URL. Hierdoor kan een grote crawl tijdens issueclassificatie
coöperatief worden beëindigd zonder een worker geforceerd te herstarten.

## Issue lifecycle

Na opslag vergelijkt de analyse-engine een snapshot met zijn voorganger en schrijft afzonderlijke
`changes`. Technische controles leveren signalen die op website, URL en type worden gededupliceerd.
Verdwenen signalen worden `resolved`, een volgende schone controle kan ze `verified` maken en een
terugkerend signaal opent hetzelfde issue opnieuw. `issue_occurrences` bewaart bewijs per crawl.

Soft-404-detectie behandelt een korte pagina nooit zelfstandig als fout. Een hard signaal vereist
status 200 plus meerdere onafhankelijke aanwijzingen uit fouttekst, vrijwel lege hoofdcontent,
afwijkende canonical of een eerdere 404/410-status. Lege zoek- en filterresultaten krijgen alleen
een contextuele review met lage zekerheid. Redirects, noindexpagina's en niet-HTML-responses vallen
buiten deze controle. Herhaalde templatepatronen worden via de bestaande clusteranalyse gebundeld.

## Asset- en mediaregister

Afbeeldingen, documenten, video en audio behouden hun bestaande identiteit in `urls` en hun
historische meetmomenten in `url_snapshots`. `assets` is een één-op-één productsamenvatting per
URL met actueel type, MIME-type, status, eind-URL, bestandsgrootte, ETag, Last-Modified en laatste
controle. Daardoor ontstaat geen tweede URL-register en blijven discovery, scope en normalisatie
centraal. Nieuwe volledige crawls vullen het register; bestaande snapshots worden niet destructief
herschreven. De tenantbeveiligde API kan per website, type en status filteren.

## Begrensde JavaScript-rendercontrole

Een gewone HTML-snapshot blijft altijd de primaire meetbron. Alleen actieve, indexeerbare
HTML-pagina's met concreet risico komen in aanmerking voor rendering: belangrijke URL's, vrijwel
lege statische content of ontbrekende basismetadata. De selectie is maximaal tien URL's en kiest
naast prioriteit ook verschillende padtemplates, zodat één dynamische template niet de hele
rendercapaciteit inneemt.

`render_observations` bewaart de browserwaarneming apart en verwijst naar exact één bronsnapshot.
De vergelijking legt verschillen vast in hoofdcontent, interne links, canonical, robots en
structured data. Alleen materiële verschillen leveren uitlegbare issues op. De aparte
`render-worker` verwerkt maximaal één RQ-taak tegelijk en begrenst tijd, HTML-grootte, aanvragen,
downloads en zware resources. Iedere browseraanvraag wordt opnieuw op publieke HTTP(S)-adressen
gecontroleerd. De worker draait alleen met het Compose-profiel `rendering`; daarnaast blokkeert
`RENDERING_ENABLED=false` standaard alle nieuwe rendertaken.

De container is niet aan de NAS gebonden. Zodra de geplande gaming-pc in een afzonderlijk project
als beveiligde Linux-worker is ingericht en de koppeling expliciet is goedgekeurd, kan juist deze
renderworker daar draaien met dezelfde database- en Redis-contracten. Tot dat moment geldt de pc
niet als beschikbare capaciteit en blijft een eventuele NAS-proef klein en gecontroleerd.

`category` beschrijft het technische onderwerp van een issue, zoals bereikbaarheid of interne
links. De afgeleide `scope` beschrijft hoe het product het signaal presenteert: SEO, SEO+UX,
kwaliteitscontrole, performance of redactioneel. Scope wordt centraal uit het issuetype afgeleid,
zodat historische en nieuwe issues zonder dataherschrijving dezelfde classificatie krijgen.
De eveneens afgeleide `nature` maakt zichtbaar of de meting een aantoonbaar probleem, een
contextafhankelijke controle of een optionele optimalisatie is. Prioriteit blijft daarvan losstaan.

## Aanbevelingstaken

Issues blijven de technische diagnosebron en behouden hun automatische lifecycle. De
versiebeheerde aanbevelingsbibliotheek vertaalt een eerste set concrete issuetypen naar een
taakdefinitie met primaire rol, standaardprioriteit, effort-band, stappen, gereedcriteria en
verificatiescope.

`recommendation_tasks` bewaart de menselijke uitvoering los van `issues.status`.
`recommendation_task_issues` koppelt één taak aan een of meer diagnoses en
`recommendation_task_urls` legt de rol van bron-, doel- of voorbeeld-URL's vast. De onveranderlijke
`recommendation_task_events` bewaren status- en uitvoeringshistorie. `recommendation_feedback`
registreert klantgebonden tijd, bruikbaarheid, correcties en verificatie-uitkomsten voor latere
kalibratie.

Taakstatus en verificatiestatus zijn afzonderlijk. Daardoor kan een taak uitgevoerd zijn terwijl
technische controle nog loopt, en kan een issue door een volgende crawl worden opgelost of heropend
zonder menselijke planning te overschrijven. Klantoverstijgende aggregatie is nog niet actief en
ruwe content, URL's, queries en analyticsregels verlaten nooit hun tenant.

De REST-API ontsluit de versiebeheerde typen, maakt per issue maximaal één actieve taak van
hetzelfde type aan en biedt websiteoverzicht, detail en gecontroleerde updates. Iedere lees- en
schrijfroute gebruikt bestaande tenantautorisatie; gebruikers met de klantrol houden alleen
leestoegang. Statusovergangen worden centraal gevalideerd en als taakevent en globale activiteit
vastgelegd.

De eerste interface-integratie staat in het bestaande issuedetail. Diagnose en technische
onderbouwing blijven bovenaan staan; de afzonderlijke uitvoeringstaak toont rol, effort-band,
stappen, gereedcriteria en alleen de toegestane volgende statussen. Dit voorkomt dat een menselijke
uitvoeringsstatus de automatische issue-lifecycle overschrijft.

Feedback is append-only en alleen toegestaan voor uitgevoerde of afgesloten taken. Werkelijke
minuten worden centraal omgezet naar een vaste effort-band. Gestructureerde signalen worden in het
taakevent en activity log opgenomen; vrije opmerkingen blijven uitsluitend op het klantgebonden
feedbackrecord en worden niet voorbereid voor klantoverstijgende aggregatie.

`recommendation_verifications` bewaart per toekomstige gerichte controle de taak, het type en de
scopeversie, URL-scope, regels, voor- en nasnapshots, resultaat, fout en timestamps. Een read-only
scopeplan controleert vooraf of de taak uitgevoerd is en alle vereiste URL-rollen bevat. Er wordt
nog niets gequeued: de bestaande `light_check` verwerkt een volledige website en is daarom geen
veilige executor voor een gerichte verificatie. De dedicated executor moet een vaste URL-ID-lijst
afdwingen voordat enqueueing wordt geactiveerd. Bij taakcreatie worden URL-rollen waar mogelijk
afgeleid uit het jongste issuebewijs, de bijbehorende linkgraaf en snapshot. Een bevoegde gebruiker
kan ontbrekende of onjuiste rollen binnen de websitescope corrigeren; iedere wijziging krijgt een
taakevent en activity-logregel.

## Jobs en exports

De API en scheduler schrijven eerst een persistent `crawl_job` en plaatsen daarna alleen het ID op
de passende RQ-queue. Light checks, sitemapcontroles en pagina-analyses gebruiken `crawls_light`;
volledige sitecrawls gebruiken `crawls_full`. Eén vaste worker per queue begrenst de standaard
NAS-capaciteit. De optionele Compose-profile `crawl-overflow` start één extra worker voor beide
queues en staat standaard uit. Een gedeeltelijk unieke database-index staat maximaal één `running`
crawl per website toe. Worker-recovery laat jobs
die aantoonbaar door een andere live RQ-worker worden verwerkt ongemoeid. GSC-, GA4- en Bing-imports
gebruiken de afzonderlijke queue `integrations`; exports gebruiken `exports`. Hierdoor blokkeren
langdurige data-imports geen crawls. RQ verzorgt retries met oplopende wachttijd. CSV-exporten leveren
één dataset; Excel bevat metadata
en aparte tabbladen voor URL's, issues, wijzigingen, interne links en vacatures. Het vacaturetabblad
bevat lifecycle, Google for Jobs-status, datums, sollicitatiegegevens, interne links en actieve
bevindingen, maar geen technische database-ID's. Bestanden staan in een gedeeld volume.

De scheduler gebruikt per website admission control: een rijlock serialiseert handmatige en
geplande starts, en zolang één crawl pending, actief of gepauzeerd is wordt geen tweede crawl
ingepland. Een recente volledige crawl geldt ook als recente sitemap- en light-checkmeting.
De FIFO-wachtrijpositie en actuele workercapaciteit worden bij de actieve crawljob teruggegeven.
Een derde crawlworker is configureerbaar voor een gecontroleerde NAS-capaciteitstest, maar wordt
niet impliciet gestart door alleen de configuratie te deployen.

Het versieerbare queuebeleid legt per queue waarschuwings- en admissiongrenzen, retry-intervallen
en time-outs vast. Een lager prioriteitsgetal wordt eerder behandeld. Website-instellingen bewaren
de prioriteit en maximaal toegestane crawlwachtrij; iedere crawljob bewaart de gekozen queue en de
toegepaste prioriteit als historisch bewijs. `queue_dead_letters` bewaart definitief uitgevallen
werk onafhankelijk van Redis, zodat beoordeling en gecontroleerd opnieuw aanbieden later mogelijk
blijven. De renderqueue staat in de eerste beleidsversie expliciet uit totdat begrensde rendering
wordt geïmplementeerd.

Enqueueing loopt centraal door dit beleid. Een volle queue accepteert geen extra werk. Crawlwerk
blijft dan in PostgreSQL als `waiting_for_capacity` staan en wordt door de scheduler opnieuw
aangeboden in websiteprioriteitsvolgorde. De standaardlimiet blijft één crawl per website en kan
begrensd tot vijf worden verhoogd. Sitemapwerk gebruikt een eigen `sitemaps`-queue op de lichte
worker. Definitieve RQ-uitval roept één idempotente callback aan die het dead-letterrecord bewaart;
een fout waarvoor nog een retry resteert wordt niet als definitieve uitval geregistreerd.

De interne systeemstatus toont per actieve queue workers, backlog, waarschuwingsgrens en
admissiongrens. Openstaande dead letters maken de totaalstatus `degraded`. Alleen de superuser kan
dead letters opvragen, met toelichting afsluiten of gecontroleerd opnieuw aanbieden. Herstel zoekt
altijd eerst de blijvende crawl-, integratie-, retentie-, export- of verificatietaak op en voert
opnieuw admission uit; de payload is bewijs en nooit zelfstandig uitvoerbare code.

## Automatische retentie

Iedere geslaagde of gedeeltelijk geslaagde volledige crawl maakt idempotent één
`retention_operation` per automatisch datatype aan. De scheduler zet verschuldigde, wachtende,
mislukte of onderbroken operaties op de afzonderlijke RQ-queue `maintenance`; de
integration-worker verwerkt die queue naast integraties.

Een operatie vergrendelt de websiterij per batch. De scheduler gebruikt dezelfde rijlock voor
nieuwe crawls. Voor iedere verwijdering wordt bovendien gecontroleerd dat voor de website geen
pending, actieve of gepauzeerde crawl bestaat. Daardoor kunnen crawl en retentie voor dezelfde
website niet gelijktijdig muteren, terwijl andere websites beschikbaar blijven.

Elke commit bewaart datatype, beleidsversie, voor-/narapport, verwijderd aantal, batchaantal,
status, attempts en eerstvolgende poging in PostgreSQL. De selectie wordt na een herstart opnieuw
berekend; al verwijderde records kunnen daardoor niet nogmaals worden verwijderd. De nieuwste
volledige crawl, nieuwste locatiehoudende snapshot per URL, actieve crawls, issuebewijs en
verificatiebewijs blijven beschermd. Dagelijkse GSC-, GA4- en Bing-data blijft minimaal 1.098
dagen beschikbaar; interne linkdetails 180 dagen plus beschermd bewijs. Snapshots en wijzigingen
worden alleen geaudit. Per queue-uitvoering geldt een harde limiet van 50.000 rijen. Resterend werk
wordt later automatisch hervat. Het volledige beleid staat in `docs/retention-policy.md`.

Google-imports halen onafhankelijke rapporten gelijktijdig op. GSC vervangt pagina- en
zoektermmetrics voor het geïmporteerde datumbereik transactioneel; GA4 doet hetzelfde voor
landingspagina-, event- en landingspagina-eventmetrics. Inserts worden in batches van maximaal
5.000 mappings uitgevoerd. Iedere synchronisatie bewaart totale, API- en databaseduur zodat
productieverschillen meetbaar blijven.

De dagelijkse Search Console-synchronisatie inspecteert daarnaast een kleine selectie URL's uit
Googles bestaande index. De selectie geeft voorrang aan handmatig belangrijke URL's, actieve
indexatieproblemen en recente wijzigingen. Een resultaat blijft zeven dagen geldig; standaard
worden maximaal 25 URL's per uitvoering en nooit meer dan 200 per handmatige batch opgevraagd.
Iedere observatie blijft historisch bewaard. De API gebruikt dezelfde read-only OAuth-scope als
de GSC-import en doet nadrukkelijk geen live-indexeerbaarheidstest.

Na opslag vergelijkt de issue-engine de observatie met de nieuwste snapshot en sitemapintentie.
Alleen belangrijke of in de sitemap opgenomen 200-pagina's met een indexeerbare crawlerstatus
kunnen een hard Google-conflict krijgen. Wanneer een relevante canonical-, robots-, status- of
indexeerbaarheidswijziging nieuwer is dan Googles laatste crawl, blijft de afwijking context totdat
Google opnieuw heeft gecrawld. Een volgende geslaagde inspectie doorloopt de normale issue-lifecycle
naar opgelost en daarna geverifieerd.

## Crawl-diepte

Een volledige sitecrawl start op de genormaliseerde basis-URL met diepte 0 en verwerkt interne
links breadth-first. De frontier combineert de basis-URL, actuele sitemap-URL's, interne links en
alle eerder bekende actieve URL's. Nieuw ontdekte URL's worden binnen dezelfde crawl ingepland.
Intern bereikbare URL's worden vóór sitemap-only en eerder bekende seeds verwerkt, zodat de kortste
gevonden afstand vanaf de basis-URL betrouwbaar als `urls.crawl_depth` wordt opgeslagen. URL's die
alleen uit een sitemap of eerdere crawl bekend zijn en niet intern bereikbaar zijn, worden wel
gecontroleerd maar houden een lege diepte.

Na de breadth-first crawl worden actieve sitemap-URL's met een lege diepte als orphan page
gemarkeerd. Het issue wordt per URL gededupliceerd en automatisch opgelost zodra de URL bij een
latere crawl wel intern bereikbaar wordt.

Een orphan-signaal bewijst alleen dat een indexeerbare sitemap-URL buiten de gecrawlde interne
structuur staat. Het systeem schrijft daarom niet automatisch extra links voor. De uitvoeringstaak
vereist eerst een inhoudelijk besluit: een bedoelde zelfstandige pagina krijgt een logische,
crawlbare plek in de sitestructuur; een overbodige pagina wordt samengevoegd of doorgestuurd en
daarna uit de sitemap verwijderd. Een belangrijke pagina die al in de structuur staat maar te
weinig inkomende links heeft, blijft een afzonderlijk linkkwaliteitsprobleem.

Orphan-analyse draait alleen wanneer de breadth-first wachtrij volledig is verwerkt. Als `max_urls`
de crawl afkapt, wordt de run `partially_succeeded` en blijven bestaande orphan-statussen ongewijzigd.

Niet-HTML-assets blijven als URL en linkdoel bewaard, maar komen niet in de HTML-crawlwachtrij.

### Elementlocaties

HTML-crawls bewaren bestaande links, knoppen, H1-H3-koppen en afbeeldingen generiek in
`element_locations`. Iedere locatie hoort bij website, bron-URL, snapshot en crawlrun en bevat
zichtbare tekst, doel, element-ID, selector, XPath, fragment, volgnummer en omliggende tekst.
Issue-types worden aan dezelfde locatie gekoppeld zodra de crawler het bijbehorende signaal kan
vaststellen. De live jump gebruikt alleen een bestaand ID, unieke zichtbare tekst of aantoonbaar
unieke tekstcontext; ontbrekende elementen krijgen geen kunstmatige locatie.
Afbeeldingen en documenten krijgen een lichte HEAD-controle. Grote afbeeldingen (meer dan 2 MB) en
documenten (meer dan 5 MB) leveren afzonderlijke issues op zonder de volledige bestanden te downloaden.

Thin content is een controlesignaal voor indexeerbare HTML-pagina's met minder dan 150 woorden
hoofdcontent. Nagenoeg lege pagina's krijgen meer urgentie. Niet-indexeerbare pagina's,
zoek-/filtervarianten en duidelijke bevestigings-, login- en checkoutpagina's worden uitgesloten om
functionele pagina's niet als contentfout te behandelen.

Na een volledig afgeronde sitecrawl vergelijkt de sitebrede contentanalyse indexeerbare pagina's
met minimaal 100 woorden. Gelijke hoofdcontenthashes leveren een hard duplicaatsignaal op. Sterk
gelijkende pagina's worden met vijfwoord-shingles en een hoge overlapdrempel als controlepunt
gemarkeerd. Veelvoorkomende template-shingles worden buiten de vergelijking gehouden. De GSC-analyse
blijft daarnaast apart signaleren wanneer één zoekopdracht over meerdere landingspagina's is verdeeld;
dat is een zoekintentiesignaal en geen bewijs van dubbele tekst.
Dezelfde sitebrede stap groepeert genormaliseerde titles en meta descriptions om identieke metadata
over meerdere indexeerbare pagina's als afzonderlijke, dedupliceerbare issues te volgen.

## Consultantinzichten

Consultantinzichten blijven gescheiden van de issue-engine: ze combineren historische GSC- en
GA4-prestaties met de laatste crawl, maar maken niet automatisch een actiepunt aan. Zoekintentie-
signalen gebruiken alleen materiële vraagvolumes, een verklaarbare woorden- en intentiematch en een
beschikbare volledige snapshot. De interface toont daarom bewijs, betrouwbaarheid en een handmatige
controleactie. Dit voorkomt dat een semantische aanname als technische fout wordt gepresenteerd.

GA4-conversie-inzichten gebruiken uitsluitend de per website geselecteerde gekwalificeerde events.
De import bewaart deze events zowel als websitebrede dagtotalen als per organische landingspagina.
Hierdoor kan de consultant veel verkeer zonder leads, een relatief lage leadratio en een dalende
leadratio onderscheiden. Na introductie of wijziging van de eventselectie is een historische
GA4-synchronisatie nodig om de landingspaginaverdeling opnieuw op te bouwen.

## Bing-backlinks

De gedocumenteerde Bing Webmaster API blijft automatisch pagina- en zoektermdata ophalen en probeert
de officiële linkmethoden. Omdat die methoden bij gevulde actuele Bing-properties lege linkdata
kunnen teruggeven, geldt een leeg API-resultaat niet als bewijs voor nul backlinks en verwijdert het
geen handmatig geïmporteerde historie. De interface accepteert de drie officiële Bing-exports voor
verwijzende domeinen, pagina's en ankerteksten als één complete meting. Records worden per website
gededupliceerd; alleen een volledig gevalideerde set mag eerder actieve exportrecords deactiveren.

## Vacaturemonitor

`job_listings` bewaart de actuele, genormaliseerde toestand van herkende vacaturepagina’s per
website en URL. Herkenning gebruikt JobPosting-schema, vacature-URL-patronen en zichtbare
vacaturetekst. Google for Jobs-signalen blijven gewone, dedupliceerbare issues zodat hun bewijs,
status en lifecycle overeenkomen met andere technische bevindingen. De interne vacatureweergave
combineert deze blijvende vacaturegegevens met alleen actieve vacature-issues; geldige vacatures
verschijnen daardoor ook wanneer zij geen issue veroorzaken. Het interne hoofdoverzicht toont
klikbare vacature-indicatoren; klanten zien deze operationele monitor niet.

## Operationele status

De interne beheerweergave controleert via `/api/v1/system/status` de database, Redis en de actieve
crawl- en exportworkers. Deze status is alleen beschikbaar voor interne rollen en staat los van het
publieke health-endpoint. Een storing in deze aanvullende controle blokkeert het tonen van bestaande
crawl- en exportgegevens niet.

## Klantonboarding en domeinafbakening

Een nieuwe klant en de eerste website worden in één databasetransactie aangemaakt. Hierdoor kan de
interface geen half voltooide klant achterlaten wanneer het opslaan van de website mislukt. Klantnamen
en interne referenties worden vooraf gecontroleerd op duplicaten. De laatst geselecteerde klant en
website worden lokaal in de browser bewaard, zodat een refresh dezelfde werkcontext herstelt.

Discovery en interne-linkregistratie accepteren uitsluitend de host van de ingestelde basis-URL, de
www-variant daarvan en expliciet geconfigureerde `allowed_subdomains`. URL's van andere domeinen in
een gedeelde sitemap of CMS worden niet geregistreerd; eerder geregistreerde externe URL's worden
vóór ieder crawltype gedeactiveerd en niet opnieuw gecrawld. Het standaard URL-overzicht toont alleen
actieve URL's; historische records blijven expliciet opvraagbaar voor audit en exports.

## Gerichte aanbevelingsverificaties

Een uitgevoerde aanbeveling kan een aparte `recommendation_verification` starten. De API bevriest
de URL-ID's en rollen in de verificatiescope en maakt een eigen crawltaak en crawlrun aan. De
dedicated worker haalt alleen de URL's op die voor de regel nodig zijn; hij start geen discovery,
sitebrede analyse of issueherberekening. HTTP-beveiliging, redirects, robotsregels, extractie en
snapshots gebruiken dezelfde services als reguliere crawls.

Regelresultaten, voor- en nasnapshot-ID's, fouten en tijden blijven bij de verificatie bewaard.
Taakstatus, issuestatus en verificatiestatus veranderen onafhankelijk. Een gedeeltelijke of
mislukte controle zet een geïmplementeerde taak daarom niet automatisch terug.

De executor ondersteunt tien afgebakende taaktypen: defecte interne links, interne links naar
redirects, ontbrekende pagina's, redirectketens/-loops, indexatiecorrecties, canonicals, titles,
primaire H1-koppen, meta descriptions en structured data. Een opvolger, verwacht doel of
vergelijkingspagina is alleen verplicht wanneer de regel zonder die intentie niet betrouwbaar kan
beslissen. Voor herstel van een ontbrekende pagina blijft `new` optioneel: een rechtstreeks
herstelde HTTP 200 is eveneens een geldige uitkomst.

On-pageverificaties crawlen alle URL's met rol `changed` en optionele URL's met rol `sample`.
Titles en descriptions moeten bestaan en uniek zijn binnen die bevroren scope. H1-verificatie eist
precies één niet-lege primaire kop. Structured-dataregels gebruiken het oorspronkelijke issuetype:
een ontbrekende breadcrumb vereist `BreadcrumbList`; ongeldige JSON-LD vereist na herstel geldige,
aanwezige schema-opmaak.

# Architectuurbesluiten

Dit document bewaart blijvende technische en productkeuzes. Nieuwe besluiten worden onderaan
toegevoegd met datum, context, keuze en gevolgen. Details van de implementatie staan in
`docs/architecture.md`.

## 2026-07-14 — Bestaande functionaliteit blijft leidend

Context: de repository bevat inmiddels gebruikers, klanttoegang, GSC, GA4, Bing, rapportages en
consultantinzichten, terwijl `AGENTS.md` enkele onderdelen oorspronkelijk als later werk benoemt.

Besluit: bestaande geteste functionaliteit wordt niet verwijderd of vereenvoudigd om het oude
MVP-kader opnieuw af te dwingen. `docs/roadmap.md` bepaalt de actuele uitvoeringsvolgorde.

Gevolg: nieuwe wijzigingen moeten compatibel blijven met de huidige productiefunctionaliteit.

## 2026-07-14 — Blijvende URL-identiteit en historische snapshots

Context: wijzigingen en issuehistorie vereisen een stabiele URL-identiteit over crawls heen.

Besluit: `urls` bewaart de blijvende identiteit, `url_snapshots` de toestand per meetmoment,
`changes` de verschillen en `issues` de actiepunten. Historische snapshots worden niet verwijderd
wanneer een URL verdwijnt.

Gevolg: actuele overzichten filteren op actieve URL's; historie en exports kunnen inactieve records
bewust blijven tonen.

## 2026-07-14 — Strikte website-scope zonder klantuitzonderingen

Context: gedeelde sitemaps en CMS-links koppelden `jobsatpearle.be` aan een andere website.

Besluit: alleen de basis-host, de equivalente www/root-variant en expliciet ingestelde subdomeinen
zijn intern. Scopecontrole geldt voor discovery, interne links, handmatige registratie en iedere
crawl. Bestaande externe records worden gedeactiveerd.

Gevolg: domeinisolatie is generiek en `jobsatpearle.be` kan later zelfstandig worden toegevoegd.

## 2026-07-14 — Atomaire klantonboarding

Context: losse klant- en websiteaanmaak kan half afgemaakte klantrecords achterlaten.

Besluit: de eerste klant en website worden in één transactie aangemaakt. Onboarding valideert en
normaliseert namen en referenties en maakt standaard website-instellingen aan.

Gevolg: een fout rolt de volledige onboarding terug; vervolgstappen mogen pas na commit worden
ingepland.

## 2026-07-14 — API-autorisatie is de beveiligingsgrens

Context: de interface verbergt functies per rol, maar UI-beperkingen zijn geen beveiliging.

Besluit: iedere beschermde route gebruikt een `Principal` en dwingt globale rol, klant- of
websitetoegang aan. De API-key blijft voor technische toegang; gebruikers werken met een beveiligde
sessiecookie en klantmemberships.

Gevolg: nieuwe UI-functionaliteit moet altijd een gelijkwaardige server-side autorisatiecontrole
hebben.

## 2026-07-14 — RQ voor werk en aparte exportqueue

Context: crawls, integraties en exports mogen HTTP-verzoeken niet blokkeren.

Besluit: persistente jobs worden via Redis/RQ uitgevoerd. Crawls gebruiken de standaardqueue en
exports een aparte `exports`-queue. De scheduler maakt alleen jobs aan; workers voeren ze uit.

Gevolg: API-, worker-, export-worker- en schedulerwijzigingen worden afzonderlijk beoordeeld bij
deployment.

## 2026-07-14 — Synology-releases via controleerbaar archive

Context: directe `scp` naar NAS-paden is onbetrouwbaar gebleken.

Besluit: releases worden lokaal met `git archive` gemaakt, met SHA-256 gecontroleerd en via
`ssh ... dd of=/tmp/...` geüpload. Op de NAS wordt pas na checksumcontrole uitgepakt.

Gevolg: ieder deploymentadvies vermeldt volledig pakketpad, checksum, migrationstatus en alleen de
geraakte containers.

## 2026-07-14 — Onpage- en noindex-issues vereisen indexatiecontext

Context: bewust niet-indexeerbare login-, filter- en hulppagina's veroorzaakten onnodige meldingen
over ontbrekende metadata, koppen en noindex-instructies.

Besluit: onpage-controles voor title, meta description en H1 gelden alleen voor indexeerbare
200-pagina's. Een noindex wordt alleen als onverwacht issue gemeld wanneer de URL in de actuele
sitemap staat of aantoonbare recente organische waarde heeft.

Gevolg: de actielijst bevat minder ruis, terwijl belangrijke pagina's met een onbedoelde noindex
met hoge urgentie gemeld blijven worden.

## 2026-07-14 — Semantische vergelijking voor wijzigingsdetectie

Context: CMS'en kunnen witruimte in koppen en de volgorde van JSON-LD `@graph`-onderdelen wijzigen
zonder dat de inhoud of betekenis verandert.

Besluit: H1-waarden worden voor vergelijking op witruimte genormaliseerd. JSON-LD-scriptblokken,
`@graph`-onderdelen en meervoudige `@type`-waarden worden als ongeordend vergeleken. De volgorde van
betekenisvolle lijsten, zoals `itemListElement`, blijft wel relevant.

Gevolg: technische herschikking veroorzaakt geen wijzigingsmelding, maar inhoudelijke structured
data-veranderingen blijven aantoonbaar zichtbaar.

## 2026-07-14 — Verouderde content alleen signaleren met expliciete datum

Context: ouderdom afleiden uit losse jaartallen of tekst levert te veel fout-positieve meldingen op.

Besluit: algemene contentouderdom wordt alleen als controlesignaal aangemaakt voor indexeerbare
redactionele schema's (`Article`, `BlogPosting`, `NewsArticle` en `TechArticle`) met een expliciete
`dateModified` of `datePublished` van minimaal drie jaar oud. Het signaal krijgt lage urgentie en
lage zekerheid; vacatures behouden hun eigen strengere verloopcontrole.

Gevolg: consultants krijgen een onderbouwde aanleiding voor inhoudelijke beoordeling zonder dat
ouderdom automatisch als SEO-fout wordt gepresenteerd.

## 2026-07-14 — Alleen typeerbare crawlerfouten worden issues

Context: mislukte verzoeken werden wel als snapshotfout opgeslagen, maar time-outs en
redirectloops ontbraken als bruikbare actiepunten. Tegelijk zijn generieke netwerkfouten vaak
tijdelijk en onvoldoende specifiek.

Besluit: crawlerfouten krijgen een intern fouttype. Alleen een bevestigde time-out en redirectloop
maken automatisch een reachability-issue aan. Andere verzoekfouten blijven beschikbaar in de
crawlhistorie. Een volgende succesvolle controle zet het eerdere issue via de normale lifecycle op
opgelost.

Gevolg: kritieke bereikbaarheidsproblemen zijn direct uitvoerbaar zonder iedere tijdelijke
verbindingstoring als nieuw SEO-issue te presenteren.

## 2026-07-14 — Crawlbesturing is coöperatief en hervatbaar

Context: een worker-restart of maximale RQ-taakduur kon een crawl afbreken terwijl de database op
`running` bleef staan. Gebruikers konden een lange crawl bovendien niet pauzeren of stoppen.

Besluit: pauze en stop worden tussen URL-verzoeken verwerkt, zodat de huidige fetch gecontroleerd
kan afronden. Een gepauzeerde crawl bewaart dezelfde job en crawlrun; hervatten reconstrueert de
resterende wachtrij uit snapshots en crawl-dieptes. Bij een worker-restart worden actieve crawls
automatisch gepauzeerd en expliciete stopverzoeken afgerond. De RQ-limiet voor crawls is zes uur.

Gevolg: deelresultaten blijven behouden, een crawl kan veilig hervatten en een containerupdate laat
geen onzichtbare `running`-status meer achter.

## 2026-07-15 — Deployments gebruiken een persistente globale crawl-drain

Context: het vervangen van een worker onderbrak actieve crawls. Handmatig alle crawls pauzeren is
foutgevoelig en mag bestaande handmatige pauzes niet overschrijven.

Besluit: een singleton in PostgreSQL blokkeert tijdens deployment nieuwe crawls uit API,
onboarding en scheduler. Actieve crawls krijgen coöperatief een pauzeverzoek en ronden hun huidige
URL af. De drain bewaart exact welke jobs hij zelf pauzeerde. Hervatten start uitsluitend die jobs;
een mislukte deployment laat de drain actief en de crawls gepauzeerd.

Gevolg: toekomstige deployments beginnen met `python -m app.maintenance pause-crawls --wait` en
eindigen pas na een geslaagde healthcheck met `python -m app.maintenance resume-crawls`.

## 2026-07-15 — Pagina-exports bewaren de exacte zichtbare selectie

Context: filters opnieuw uitvoeren in de export-worker kan een andere uitkomst geven wanneer data
tussentijds wijzigt of wanneer UI- en backendfilterlogica uiteenlopen.

Besluit: de pagina's URL's, Wijzigingen en Vacatures sturen de ID's van de volledige gefilterde
selectie mee. De exportjob bewaart deze ID's en een leesbare filtersamenvatting. CSV-bestanden
bevatten daarnaast website, UTC-exporttijd en filters als vaste contextkolommen.

Gevolg: een pagina-export is reproduceerbaar en bevat uitsluitend de selectie die bij het starten
zichtbaar was; een lege selectie valt niet terug op alle records.

## 2026-07-15 — Databasepoolverbindingen zijn procesgebonden

Context: RQ maakt voor jobs een childproces. De worker had tijdens herstel al een PostgreSQL-
verbinding geopend, waardoor het childproces die verbinding en psycopg prepared statements erfde.
Een hervatte HUMAN-crawl mislukte daardoor met `DuplicatePreparedStatement`.

Besluit: iedere SQLAlchemy-verbinding bewaart het proces-ID waarin zij is geopend. Bij checkout in
een ander proces wordt de geërfde verbinding ongeldig gemaakt en transparant opnieuw geopend.

Gevolg: crawls en andere RQ-jobs delen nooit een fysieke databaseverbinding met het workerproces;
prepared-statementstatus en transactiestatus kunnen niet meer over een fork lekken.

## 2026-07-15 — Crawldiepte toont de volledigheid van de broncrawl

Context: een volledige crawl wist bij de start de vorige dieptes. Tussenresultaten van een lopende
of mislukte crawl werden daarna zonder voorbehoud als actuele crawldiepte getoond.

Besluit: het URL-overzicht koppelt de getoonde diepte aan de status van de laatste volledige crawl.
Alleen een geslaagde crawl levert een betrouwbare kortste route of een betrouwbare conclusie dat
geen interne route is gevonden. Andere waarden worden expliciet als voorlopig of onvolledig
gemarkeerd. De crawler overschrijft een al gevonden kortere route niet met een langere wachtrijroute.

Gevolg: een waarde zoals diepte 2 is controleerbaar als resultaat van een voltooide crawl en het
URL-detail reconstrueert de concrete kortste route uit de links van die crawl. Resultaten van een
afgebroken crawl kunnen niet langer voor definitieve structuurdata worden aangezien.

## 2026-07-15 — Wijzigingscontext wordt afgeleid, niet als oordeel opgeslagen

Context: losse technische verschillen misten vergelijkingsdata en uitleg. Daardoor leek iedere
wijziging even belangrijk en was niet duidelijk wat gecontroleerd moest worden.

Besluit: de API combineert de bestaande vorige en huidige snapshots met een vaste, testbare
context per wijzigingstype: relevantieniveau, mogelijke betekenis en aanbevolen controle. Deze
duiding wordt afgeleid en niet redundant in `changes` opgeslagen.

Gevolg: historische wijzigingen profiteren direct van betere uitleg zonder dat data hoeft te worden
herschreven; indexatiekritieke wijzigingen krijgen meer nadruk dan description- of schemaverschillen.

## 2026-07-15 — Onbereikbare URL-doelen stoppen een sitecrawl niet

Context: HUMAN liep na 3.560 pagina's volledig stuk op `http://human.nl/alvriend`, omdat een niet
oplosbare hostname als onverwachte systeemfout buiten de normale URL-foutafhandeling viel.

Besluit: URL- en DNS-validatiefouten worden als herstelbare `invalid_target`-crawlerfout opgeslagen.
Ze verhogen het aantal mislukte URL's, maken een bereikbaarheidsissue aan en laten de crawl
doorlopen. Een mislukte job met bestaande snapshots mag vanuit dezelfde crawlrun hervatten.

Gevolg: een beperkt aantal onbereikbare links resulteert in `partially_succeeded` in plaats van een
afgebroken sitecrawl; opgeslagen voortgang hoeft na een gerepareerde crawlerfout niet opnieuw.

## 2026-07-15 — De publieke website vertelt het productverhaal tijdens scrollen

Context: de publieke pagina vóór de login legde de kern kort uit, maar liet onvoldoende zien hoe
SEO Monitor signalen omzet in bruikbare acties.

Besluit: kleuren en typografie blijven behouden. De publieke landingspagina krijgt een ruime hero,
productvisuals en een vierdelig scrollverhaal. Links verandert de uitleg; rechts worden prioriteiten,
wijzigingen, sitestructuur en actiebeheer zichtbaar. Het ingelogde dashboard blijft operationeel en
compact. Op kleinere schermen wordt de presentatie een gewone verticale stroom.

Gevolg: bezoekers begrijpen vóór het inloggen zowel de waarde als de werkwijze van het product,
zonder dat de interface voor bestaande gebruikers verandert.

## 2026-07-15 — Een ontbrekende vacature-identifier is alleen contextueel een issue

Context: `identifier` en `employmentType` zijn aanbevolen JobPosting-velden. Het ontbreken ervan
werd op iedere vacature als laag issue getoond, terwijl dit meestal slechts een optimalisatie is.
Een identifier wordt pas operationeel belangrijk wanneer sterk gelijkende vacatures zonder stabiele
identiteit moeilijk uit elkaar te houden zijn.

Besluit: ontbrekende aanbevolen velden leveren niet langer zelfstandig een issue op. Na een volledige
sitecrawl vergelijkt SEO Monitor alle indexeerbare JobPosting-pagina's zonder identifier. Alleen een
groep met minimaal twee sterk gelijkende vacatures krijgt een contextueel signaal. Vanaf vijf
vacatures is de ernst middel en het vertrouwen hoog; kleinere groepen blijven laag met gemiddeld
vertrouwen.

Gevolg: de generieke waarschuwing verdwijnt. Een nieuw signaal benoemt de omvang, inhoudelijke
overlap en gerelateerde URL's, zodat de aanbevolen identifier een aantoonbaar probleem oplost.

## 2026-07-15 — Een sitemapjob zonder sitemap mag niet slagen

Context: de scheduler maakte voor iedere website dagelijks een sitemapjob. Wanneer
`website_settings.sitemap_urls` leeg was, rondde de worker die job zonder netwerkverzoek af als
geslaagd met overal nul. Daardoor leek een niet-uitgevoerde import succesvol.

Besluit: sitemapimport combineert ingestelde URL's met `Sitemap:`-regels uit `robots.txt`. Als beide
ontbreken, wordt gecontroleerd `/sitemap.xml` geprobeerd. Een succesvolle ontdekking wordt in de
website-instellingen bewaard. De run telt unieke gevonden URL's en gelezen sitemapdocumenten. Als
geen sitemap bestaat, eindigt de job expliciet als mislukt met een begrijpelijke reden.

Gevolg: lege succesregels verdwijnen, websites zonder handmatige sitemapconfiguratie worden toch
automatisch ontdekt en dubbele URL's vertekenen de telling niet.

## 2026-07-15 — Intelligentie betekent bewijs, verband en uitvoerbare diagnose

Context: losse issues met een generieke beschrijving en actie leveren onvoldoende advieswaarde.
Honderd vergelijkbare URL-signalen zijn vaak symptomen van één template-, filter-, paginering- of
canonicalprobleem. Een lange lijst of korte samenvatting helpt dan niet bij de werkelijke oplossing.

Besluit: SEO Monitor ontwikkelt van signaaldetector naar diagnoseplatform. Deterministische analyse
vormt eerst URL-cohorten, herkent patronen en koppelt signalen over crawls en databronnen. Een
diagnose scheidt feitelijk bewijs, interpretatie en hypothese; toont vertrouwen en alternatieven; en
geeft concrete aanpassing plus verificatiecriterium. Taalmodellen mogen later uitleg en aanvullende
hypothesen ondersteunen, maar uitsluitend op meegeleverd bewijs en nooit als ongecontroleerde bron.

Gevolg: de primaire eenheid in de interface wordt waar mogelijk één onderliggende diagnose met
geraakte URL's, niet een los issue per URL. UX-polish richt zich op uitzonderingen, beslissingen en
progressieve uitleg in plaats van meer tabellen of decoratie.

## 2026-07-16 — Bulkafhandeling heeft een expliciete blijvende scope

Context: dezelfde handmatig beoordeelde signalen opnieuw afhandelen na iedere crawl veroorzaakt
ruis. Alleen een status `resolved` is daarvoor onvoldoende: de huidige issue-engine opent een
terugkerend signaal terecht opnieuw, terwijl de gebruiker sommige combinaties van URL en issuetype
bewust blijvend wil afsluiten.

Besluit: de interface maakt onderscheid tussen oplossen met verificatie en blijvend afhandelen.
Een blijvende bulkafhandeling wordt apart opgeslagen per website, URL en issuetype, inclusief actor,
moment en toelichting. De issue-engine onderdrukt daarna alleen exact die combinatie. Andere
issuetypen op dezelfde URL en hetzelfde type op nieuwe URL's blijven nieuwe signalen opleveren.
Iedere onderdrukking blijft zichtbaar, controleerbaar en omkeerbaar.

Gevolg: bulkacties besparen terugkerend handwerk zonder nieuwe problemen breed of onzichtbaar weg
te filteren. `Fixed` en `ignored` krijgen een voorspelbare, auditbare betekenis.

## 2026-07-16 — Interne-linkissues worden ook per bronpagina geclusterd

Context: meerdere dode links op één artikel verschenen als afzonderlijke issues voor de defecte
doel-URL's. Technisch klopt ieder signaal, maar redactioneel is het één taak: open de bronpagina en
herstel daar alle defecte links tegelijk.

Besluit: de diagnose-engine ondersteunt een bronpaginaweergave naast doelgerichte analyse. Per
bronpagina en linkprobleem ontstaat één hoofdissue met een lijst van onderliggende links. Iedere
link bewaart doel-URL, ankertekst, fout/status en historie. De losse bewijzen blijven beschikbaar,
maar worden niet als concurrerende hoofdissues in de actielijst gepresenteerd.

Gevolg: een pagina met vier dode interne links levert één uitvoerbare taak op. Tegelijk kan een
defect doel dat vanaf veel pagina's wordt gelinkt afzonderlijk als sitebreed patroon worden herkend.

## 2026-07-16 — AI doet gegronde voorstellen en neemt geen beslissingen over

Context: een generiek advies zoals “verbeter de meta description” laat het moeilijkste werk bij de
gebruiker. Een taalmodel kan bruikbare concepten maken wanneer het beschikt over actuele
pagina-inhoud, zoekintentie, merkstijl en zorgvuldig gekozen vergelijkingspagina's.

Besluit: AI wordt een optionele, verwisselbare advieslaag boven op de deterministische diagnose.
Prompts ontvangen alleen noodzakelijke, niet-gevoelige bewijscontext. Voorstellen benoemen hun
bronnen en onzekerheid, bieden waar nuttig meerdere varianten en worden nooit automatisch
gepubliceerd. De gebruiker keurt goed, past aan of wijst af. “Beste pagina's” worden niet uitsluitend
op CTR gekozen, maar binnen vergelijkbare paginatypen en met positie en andere vertekening in beeld.

Gevolg: de tool levert concretere teksten en acties zonder feitelijke analyse aan een taalmodel uit
te besteden. Providerkeuze, kostenlimieten, privacy en menselijke controle blijven expliciete
productvoorwaarden.

## 2026-07-16 — Bing-data blijft een expliciete aanvullende zoekbron

Context: de OAuth-koppeling en propertyselectie bestonden al, maar Bing-pagina-, zoekterm- en
inkomende-linkdata werden nog niet geïmporteerd. Daardoor kon de tool Bing niet naast Google
beoordelen en bleef officiële linkdata onbenut.

Besluit: Bing-statistieken krijgen eigen dagelijkse tabellen voor pagina's en zoektermen. Imports
vervangen idempotent de gekozen periode, koppelen genormaliseerde pagina-URL's aan het URL-register
en bewaren ongekoppelde regels. Handmatige en geplande synchronisatie gebruiken dezelfde service.
Dezelfde import haalt officiële linkaantallen, verwijzende pagina's en ankerteksten op en bewaart
eerste en laatste waarneming. Links worden alleen als verdwenen gemarkeerd wanneer het betreffende
doel volledig opnieuw is opgehaald. Inzichten noemen Bing altijd als bron en trekken geen
zoekmachinebrede conclusie uit alleen Bing.

Gevolg: Bing-dalingen kunnen naast GSC worden beoordeeld zonder databronnen te vermengen. Omdat de
officiële Bing-statistieken volgens Microsoft periodiek worden bijgewerkt, interpreteert de tool de
data op periodebasis en niet als realtime signaal. Bereikte API-veiligheidslimieten worden als
gedeeltelijke dekking opgeslagen in plaats van als afwezigheid geïnterpreteerd.

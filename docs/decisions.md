# Architectuurbesluiten

Dit document bewaart blijvende technische en productkeuzes. Nieuwe besluiten worden onderaan
toegevoegd met datum, context, keuze en gevolgen. Details van de implementatie staan in
`docs/architecture.md`.

## 2026-07-17 — Bing-backlinks gebruiken een officiële exportfallback

Context: HUMAN toont in Bing Webmaster Tools 712 verwijzende domeinen en 20,5 duizend verwijzende
pagina's, terwijl de gedocumenteerde `GetLinkCounts`-methode voor dezelfde property leeg antwoordt.

Besluit: API-synchronisatie blijft beschikbaar, maar een leeg linkantwoord wordt niet als nulmeting
geïnterpreteerd. SEO Monitor importeert daarnaast de officiële Referring Domains, Referring Pages en
Referring Anchors CSV-bestanden gezamenlijk. Pas na validatie van alle drie bestanden wordt de meting
opgeslagen en mogen ontbrekende oude exportrecords inactief worden.

Gevolg: backlinkdata blijft reproduceerbaar en herhaalbaar zonder scraping van het Bing-portaal.
De databron en het importmoment blijven zichtbaar in de integratie-instellingen.

## 2026-07-17 — Een volledige crawl combineert alle actieve discoverybronnen

Context: sitemapimport registreerde URL's correct, maar de full-site frontier selecteerde na het
wissen van crawldieptes alleen de basis-URL en vervolgens intern bereikbare pagina's. Daardoor kon
een crawl 51 pagina's verwerken terwijl 93 sitemap-URL's en 106 actieve bekende URL's bestonden.

Besluit: de full-site frontier start met alle actieve HTML-URL's uit sitemap, interne discovery en
historie. Intern vanaf de basis-URL bereikbare pagina's houden voorrang, zodat breadth-first diepte
correct blijft. Sitemap-only en eerder bekende pagina's worden ook gecontroleerd, maar krijgen
alleen een diepte wanneer een echte interne route wordt gevonden. `discovered_urls` telt de unieke
volledige frontier; `crawled_urls` telt succesvolle verzoeken.

Gevolg: full-site crawls controleren niet langer alleen de intern verbonden component. Hervatten
reconstrueert dezelfde gecombineerde frontier uit actieve URL's en bestaande snapshots.

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
`ssh ... dd of=/tmp/...` geüpload. SCP en Git op de NAS worden niet gebruikt. Na checksumcontrole
wordt altijd met `sudo tar` uitgepakt, omdat de productiebestanden root-owned zijn. De operator
werkt met twee vaste terminalvensters: de upload gebeurt vanuit de lokale Mac-shell; controle,
uitpakken en Docker-handelingen gebeuren in de al geopende interactieve NAS-shell. Er wordt na de
upload geen tweede SSH-login gestart.

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

Implementatie: `issue_suppressions` bewaart de exacte scope en herstelstatus. De bulk-API maakt
onderscheid tussen `resolve_and_recheck` en `suppress_issue_type`; herstel activeert het bestaande
issue opnieuw voor beoordeling. Iedere actie wordt daarnaast in `activity_log` vastgelegd.

Gevolg: bulkacties besparen terugkerend handwerk zonder nieuwe problemen breed of onzichtbaar weg
te filteren. `Fixed` en `ignored` krijgen een voorspelbare, auditbare betekenis.

## 2026-07-18 — Handelingsadvies blijft bewijsgebonden en verklaart onzekerheid

Context: een aanbeveling is pas bruikbaar wanneer duidelijk is wat gemeten is, wat het systeem
daaruit afleidt en wat nog slechts een mogelijke verklaring is. Een generieke oorzaaktekst kan
anders meer zekerheid suggereren dan de crawl werkelijk levert.

Besluit: issuedetails krijgen centraal opgebouwde guidance met relevantie, waarschijnlijke oorzaak,
alternatieve verklaring, concrete stap en verificatie. Opgeslagen diagnosevelden hebben voorrang.
Ontbreekt oorzaakbewijs, dan beschrijft de tool alleen de waarneming en vraagt om menselijke
controle. De interface labelt feitelijke meting, systeeminterpretatie en hypothese afzonderlijk.

Gevolg: adviezen blijven reproduceerbaar vanuit opgeslagen data en kunnen later door een modulaire
AI-laag worden verrijkt zonder AI-conclusies met crawlerfeiten te vermengen.

Productiecorrectie: oorzaak en alternatieve verklaring zijn optioneel. Zonder opgeslagen
diagnosebewijs worden die secties niet gevuld met generieke tekst. Issuedetails laden bovendien
uitsluitend elementlocaties en 28-daagse impact voor de gekozen URL of het gekozen linkdoel; nooit
meer standaard voor de volledige crawl of website.

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

## 2026-07-16 — Dode interne links worden ook per bronpagina gegroepeerd

Context: meerdere dode links op één artikel werden uitsluitend als losse problemen op de
doel-URL's gepresenteerd. Daardoor bleef de feitelijke redactietaak — één bronpagina nalopen —
verborgen en ontstond onnodige ruis.

Besluit: vanaf twee verschillende dode interne links krijgt de bronpagina één aanvullende diagnose.
Het bewijs bewaart per link de doel-URL, ankertekst en status. De diagnose verdwijnt automatisch
wanneer een volgende volledige crawl minder dan twee dode links op die pagina vindt. Doelgerichte
404-diagnoses blijven beschikbaar voor het andere patroon: één defect doel waar meerdere pagina's
naartoe verwijzen.

Gevolg: de interface kan een pagina als één uitvoerbare reparatietaak presenteren zonder de
onderliggende linkgegevens of sitebrede doelanalyse te verliezen.

## 2026-07-16 — Identifier-risico wordt één vacaturetemplatediagnose

Context: de contextuele identifiercontrole voorkwam al meldingen voor losse optionele velden, maar
maakte binnen een aantoonbaar gelijkende groep nog één issue per vacature. Een templatefout werd
daardoor alsnog als tientallen afzonderlijke taken gepresenteerd.

Besluit: alle inhoudelijk gelijkende vacatureclusters zonder identifier worden per website in één
diagnose samengebracht. Het issue toont het totale aantal geraakte vacatures, de afzonderlijke
clusters, de minimale inhoudsoverlap en alle URL's. Prioriteit en vertrouwen volgen de grootste
cluster. Bestaande URL-specifieke identifierissues worden bij een volgende volledige crawl opgelost.

Gevolg: GrandVision krijgt één uitvoerbare templateactie in plaats van herhaling per vacature.
Ontbrekende optionele velden blijven zonder aantoonbaar risico buiten de actieve issuelijst.

## 2026-07-17 — Samenhangende 404-reeksen worden één patroondiagnose

Context: HUMAN bevat paginerings- en parameter-URL's die als losse 404-issues werden getoond. De
afzonderlijke URL's zijn bewijs, maar de uitvoerbare oorzaak zit waarschijnlijk in één template,
filter of navigatieregel.

Besluit: expliciete paginering wordt vanaf twee 404-URL's gegroepeerd; algemene parameterreeksen
vanaf drie. De diagnose bewaart patroon, type, omvang en alle URL's, en onderscheidt een
waarschijnlijke oorzaak van een alternatieve verklaring. Onderliggende URL-issues blijven in de
database voor historie, maar verdwijnen uit het hoofdissue-overzicht zolang de patroondiagnose
actief is.

Gevolg: één technische aanpassing wordt één taak. Wanneer een volgende volledige crawl het patroon
niet meer aantreft, wordt de diagnose opgelost en vervalt de onderdrukking van losse URL-signalen.

## 2026-07-17 — Een foutpagina telt niet als eigen interne linkbron

Context: sommige 404-templates bevatten een link naar de aangevraagde URL zelf. Daardoor verscheen
de defecte doel-URL ook tussen de pagina's die naar zichzelf verwezen en werd het aantal bruikbare
interne linkbronnen met één overschat.

Besluit: links waarbij bron- en doelrecord gelijk zijn tellen niet mee voor contextuele 404-impact,
de bronpaginaweergave en groepering van meerdere dode links. De ruwe link blijft wel in de
crawlhistorie bewaard.

Gevolg: de gebruiker ziet uitsluitend andere pagina's waarop de defecte link daadwerkelijk moet
worden hersteld.

## 2026-07-17 — Live elementjumps gebruiken alleen opgeslagen betrouwbaar bewijs

Context: issuebewijs benoemde URL's en aantallen, maar wees het betrokken bestaande DOM-element niet
aan. Een generieke visuele inspectiemodus is waardevol, maar vraagt rendering, overlays en een
aanzienlijk bredere architectuur.

Besluit: de eerste versie bewaart links, knoppen, H1-H3-koppen en afbeeldingen generiek per
snapshot. Een live jump gebruikt eerst een element-ID, daarna unieke zichtbare tekst en pas daarna
unieke prefix-/suffixcontext. Zonder betrouwbaar doel toont de interface alleen bronpagina,
selector, XPath, fragment en tekstcontext. De klantwebsite wordt nooit aangepast. Ontbrekende
elementen vallen expliciet buiten deze eerste versie.

Gevolg: gebruikers kunnen bestaande probleemlocaties sneller vinden zonder schijnzekerheid. Een
volwaardige gerenderde inspectiemodus blijft als laatste roadmapfase apart gepland.

## 2026-07-17 — Het URL-overzicht toont actieve diagnoses

Context: de URL-tabel liet vooral status, indexatie en crawldiepte zien. Een indexeerbare maar
nagenoeg lege pagina kon daardoor als een normale regel ogen, terwijl de bestaande thin-contentcheck
wel degelijk een actief issue had aangemaakt.

Besluit: iedere URL-regel toont voortaan het belangrijkste actieve issue, de hoogste prioriteit en
het aantal aanvullende signalen. Opgeloste, geverifieerde en genegeerde issues tellen niet mee.
Crawldiepte behoudt de meetcontext en de detailweergave toont de kortste gevonden route.

Gevolg: het URL-overzicht wordt een uitzonderingen- en beslissingenlijst zonder bestaande
crawlgegevens of issuehistorie te dupliceren.

## 2026-07-19 — Crawlbesturing geldt ook tijdens sitebrede na-analyse

Context: een HUMAN-light-check had alle 5.365 URL's verwerkt, maar bleef tijdens de daaropvolgende
404-classificatie op `running`. Een stopverzoek werd pas tussen URL-verzoeken gecontroleerd en kon
daardoor niet meer zonder workerrestart worden afgehandeld.

Besluit: potentieel lange sitebrede analyses ontvangen dezelfde coöperatieve controle als de
crawllus. De 404-classificatie controleert vóór en tijdens verwerking van URL's, linkregels en
bronpagina's op pauze- en stopverzoeken.

Gevolg: een grote crawl kan ook na het laatste netwerkverzoek tijdig worden gepauzeerd of gestopt;
deelresultaten blijven behouden en een workerrestart is niet langer de normale uitweg.

## 2026-07-19 — Issues onderscheiden onderwerp en productscope

Context: de goedgekeurde issue-audit onderscheidt harde SEO-problemen van UX-, performance-,
redactionele en semantische controles. De bestaande `category` benoemt alleen het technische
onderwerp en kon dat verschil niet zichtbaar maken.

Besluit: de API leidt centraal een `scope` af uit het issuetype. Bestaande categorieën en issue-
historie blijven intact. Afbeeldings-, kopstructuur- en dieptesignalen worden kwaliteitscontrole,
bestandsgrootte wordt performance en mogelijke contentouderdom wordt redactioneel gepresenteerd.
Daarnaast onderscheidt `nature` aantoonbare problemen, contextafhankelijke controles en optionele
optimalisaties. 410, robotsblokkade, beperkte content, bijna-duplicaten, ontbrekende H1 en zwakke
interne ondersteuning vragen controle; meta descriptions en breadcrumbmarkup zijn optimalisaties.

Auditcorrectie: een redirectketen van meer dan drie stappen blijft zichtbaar, maar met lage
prioriteit en zonder een niet-onderbouwde harde norm van maximaal één stap. Contextueel risico op
vacature-identifiers wordt als kwaliteitsoptimalisatie gepresenteerd, niet als bewezen SEO-fout.

Gevolg: gebruikers kunnen technische SEO-issues apart filteren zonder nuttige controles te
verwijderen of ze ten onrechte als harde SEO-fout te presenteren.

## Pagineringsreeksen als één templatecontrole

Metadata, canonical, crawldiepte en lege grenspagina's worden per pagineringsreeks samengebracht in
één websitebrede diagnose. De URL-issues en historie blijven opgeslagen, maar de actieve actielijst
verbergt deze kinderen zolang de groepsdiagnose actief is. Een volgende volledige crawl werkt het
bewijs bij en lost de diagnose op wanneer de reeks geen afwijkingen meer bevat.

Gevolg: tientallen pagina's met hetzelfde templategedrag leveren één controleerbare taak op, zonder
feitelijke metingen of historie te verwijderen.

## Redirectlinks groeperen op bronpagina

Wanneer één bronpagina minimaal twee interne links naar redirect-URL's bevat, worden deze links als
één bronpaginataak gepresenteerd. De afzonderlijke redirectdoelen en historie blijven opgeslagen;
doelen die niet door een brongroep worden gedekt blijven als zelfstandige taak zichtbaar. De
groepsdiagnose bevat per link de oude URL, eind-URL, ankertekst en status.

`deep_page` blijft beschikbaar als kwaliteitscontrole, maar wordt als contextafhankelijke controle
gelabeld in plaats van als bewezen probleem.

Gevolg: de actielijst volgt het niveau waarop de wijziging kan worden uitgevoerd, zonder enkelvoudige
redirectproblemen of meetbewijs te verbergen.

## Herhaalde URL-signalen als templateclusters

Grote groepen met hetzelfde issuetype en een gedeelde URL-familie of metadatawaarde worden als één
websitebrede templatecontrole gepresenteerd. Drempels verschillen per signaal: drie URL's voor exact
gelijke canonicalwaarden, twee voor exact gelijke metadata, vijf voor content-, H1-, ontbrekende-veld- en orphanfamilies en tien voor
crawldiepte. Pagineringskinderen worden uitgesloten omdat die al een specifiekere reeksdiagnose
hebben. Onderliggende issues en historie blijven opgeslagen.

Kleine families die de drempel niet zelfstandig halen, worden nog één keer op het bovenliggende
padsegment beoordeeld. Een `internally_linked_404`-doeltaak verdwijnt uit de hoofdactielijst wanneer
hetzelfde doel al voorkomt in een actieve gegroepeerde bronpaginataak; het onderliggende issue blijft
opgeslagen en komt terug zodra de brongroep niet meer actief is.

Bronpagina's met exact dezelfde set gebroken links of redirects worden als één componentcluster
getoond. CMS-placeholders worden per URL-familie en aantal elementen gegroepeerd. Cloudflare's
`/cdn-cgi/l/email-protection` en onverwerkte CMS-linkwaarden zijn geen navigeerbare URL-doelen en
worden daarom niet daarnaast als 404-, broken-link- of redirectprobleem geclassificeerd.

Canonicalcontrole wordt alleen uitgevoerd op bereikbare pagina's met een 200-status. Een 404-pagina
met een canonical naar de foutpagina levert daardoor niet langer een tweede canonicalissue op.

## 2026-07-22 — Crawls en data-imports krijgen afzonderlijke begrensde capaciteit

Context: één lange websitecrawl of Google-import blokkeerde alle overige crawls en imports. Een
tweede algemene worker zou bij opstart actieve jobs van de eerste worker ten onrechte als
onderbroken kunnen pauzeren.

Besluit: twee crawlworkers delen de queue `crawls`; één importworker verwerkt `integrations` en de
bestaande exportworker blijft `exports` verwerken. Een gedeeltelijk unieke database-index begrenst
iedere website tot één `running` crawl. Recovery beschermt crawl-ID's die door een andere live
RQ-worker worden uitgevoerd. Twee crawlworkers vormen de veilige initiële NAS-capaciteitslimiet.

Gevolg: verschillende websites kunnen parallel voortgang boeken, data-imports blokkeren geen crawl
meer en een extra workerstart pauzeert geen aantoonbaar actieve crawl van een andere worker. De
primaire crawlworker luistert tijdens de overgang ook naar de oude `default`-queue, zodat reeds
ingeplande jobs na deployment niet achterblijven; nieuwe jobs gebruiken uitsluitend hun eigen queue.

## 2026-07-22 — Google-imports gebruiken parallelle rapporten en begrensde bulkinserts

Context: GSC vroeg pagina- en zoektermrapporten na elkaar op en zocht voor iedere paginarij apart
naar een bestaande metric. GA4 vroeg drie onafhankelijke rapporten sequentieel op. Vooral een eerste
historie-import van 480 dagen was daardoor onnodig traag.

Besluit: onafhankelijke GSC- en GA4-rapporten worden per bron gelijktijdig opgevraagd. Het volledige
geïmporteerde datumbereik wordt binnen één transactie vervangen en mappings worden in batches van
maximaal 5.000 rijen opgeslagen. Totale, API- en databaseduur worden bij de integratie vastgelegd en
in structured logs opgenomen.

Gevolg: GSC heeft geen rij-voor-rij databasequery meer, Google-netwerkwachttijd overlapt en grote
imports gebruiken begrensde batches. Een mislukte transactie behoudt de eerder gecommitte data.

## 2026-07-22 — Integratiestoringen worden zichtbaar en veilig diagnostisch

Context: een afgewezen OAuth-vernieuwing werd alleen als generieke fout opgeslagen en was uitsluitend
op de integratiepagina zichtbaar. Daardoor was niet te onderscheiden of opnieuw koppelen echt nodig
was en kon ontbrekende rapportagedata ongemerkt blijven.

Besluit: veilige OAuth-foutcodes worden zonder tokens of response-inhoud opgeslagen. Een verlopen,
ingetrokken of niet-ontsleutelbaar token markeert de verbinding als fout. Beheerders zien fouten van
de accountverbinding of websitemapping als waarschuwing bovenaan het technische overzicht, met een
directe route naar Integraties. Niet-geconfigureerde koppelingen geven geen waarschuwing.

Gevolg: ontbrekende GSC-, GA4- of Bing-data wordt operationeel zichtbaar en `invalid_grant` maakt
expliciet dat opnieuw koppelen nodig is. De onderliggende oorzaak kan vanaf de eerstvolgende fout
worden vastgesteld zonder secrets vast te leggen.

## 2026-07-22 — Navigatie volgt taken, analyse en beheercontext

Context: negen gelijkwaardige sidebarlinks vermengden analyse, rapportage, operaties en beheer. De
klant- en websitekeuze stond alleen in één paginaheader, terwijl dezelfde context voor vrijwel alle
werkpagina's geldt.

Besluit: de interface krijgt vijf hoofdgroepen: Overzicht, Analyse, Rapportages, Crawls & exports en
Instellingen. Analyse en Instellingen tonen alleen binnen hun actieve of geopende groep subpagina's.
Een gedeelde contextbalk bewaart de bestaande klant- en websitekeuze. De bestaande hashroutes blijven
als compatibiliteitsalias bestaan en worden naar de nieuwe canonieke hashes vervangen.

Gevolg: het dashboard bevat alleen samenvattingen en doorlinks; de volledige actielijst staat onder
Analyse > Acties. Organisatiebeheer wordt zonder API- of datamodelwijziging als Klanten & websites en
Team & toegang gepresenteerd. Autorisatie en alle inhoudelijke berekeningen blijven ongewijzigd.
## Read-only retentionaudit vóór opschoning

Databasegroei wordt eerst meetbaar gemaakt met `python -m app.maintenance retention-audit`.
Dit commando wijzigt geen data. Voor elementlocaties markeert het alleen oude, probleemvrije
locaties buiten actieve crawls, buiten de nieuwste geslaagde of gedeeltelijk geslaagde volledige
crawl en buiten de nieuwste locatiehoudende snapshot per URL als mogelijke opruimkandidaat.
Locaties met issues blijven altijd beschermd. GSC-gegevens
worden uitsluitend in leeftijdsgroepen gerapporteerd. Een daadwerkelijke bewaartermijn,
opschoning en indexwijziging volgen pas na beoordeling van de productie-uitvoer.

De elementlocatie-opschoning vereist vervolgens een actieve, veilige maintenance-pauze en een
expliciete `--confirm-delete`. De selectie wordt per website vastgezet en in kleine transacties
verwijderd. GSC-data valt nadrukkelijk niet onder dit commando.

## 2026-07-31 — Elementlocaties krijgen tabelspecifiek autovacuum

Context: `element_locations` bevatte circa 8,9 miljoen rijen. De standaard vacuümdrempel van 20%
zou bij deze omvang pas na ongeveer 1,8 miljoen wijzigingen worden bereikt. De eerste begrensde
productiepilot verwijderde voor Floris 95.295 aantoonbare kandidaten in batches van 10.000. Er
bleven 28.312 beschermde rijen over en productie bleef gezond.

Besluit: stel voor alleen `element_locations` een vacuümschaalfactor van 2% met een basisdrempel
van 50.000 in. Stel de analyseschaalfactor in op 1% met een basisdrempel van 25.000. Bij circa
8,8 miljoen rijen liggen de verwachte activeringspunten daarmee rond 226.000 respectievelijk
113.000 wijzigingen. De migratie wijzigt alleen tabelopties en kan deze opties weer resetten.

Gevolg: PostgreSQL kan vrijgekomen ruimte eerder hergebruiken en plannerstatistieken eerder
bijwerken. Dit vervangt de veilige, begrensde opschoningsvensters niet en is geen opdracht voor
`VACUUM FULL`. GSC-bewaartermijnen blijven een afzonderlijk besluit zonder automatische
verwijdering.

Back-upafweging: een extra releaseback-up is alleen toegestaan wanneer die noodzakelijk is om een
migratie veilig uit te voeren of te herstellen. Migratie `0034` wijzigde alleen omkeerbare
tabelopties, verwijderde of herschreef geen data en was eerst in staging gevalideerd. Daarom is voor
de productiemigratie bewust geen nieuwe back-up gemaakt; de bestaande geverifieerde back-up bleef
beschikbaar. Datatransformaties, destructieve schemawijzigingen en moeilijk omkeerbare
bulkmutaties vereisen wel een nieuwe, geverifieerde back-up.

Operationele vervolgmeting: bij Schipper zijn door twee handmatige aanroepen elk exact 50.000
kandidaten verwijderd. De tweede aanroep volgde na een terminalonderbreking. Daarom wordt een
onderbroken verwijdercommando voortaan altijd als mogelijk uitgevoerd beschouwd. Eerst volgt een
read-only telling en nieuwe retentionaudit; direct opnieuw uitvoeren is niet toegestaan.

Statuscorrectie: na het hervatten werd een normaal draaiende `human.nl`-lightcheck ten onrechte als
`waiting=1` getoond terwijl de maintenance-pauze al inactief was. `waiting` beschrijft voortaan
alleen crawls waarop een actieve drain nog wacht. Reguliere actieve crawls maken een inactieve
maintenance-status niet langer onrustwekkend.

## Compacte GSC-deduplicatiesleutels

De unieke GSC-indexen bevatten volledige URL- en zoektermteksten en zijn daardoor groter dan nodig.
Dagelijkse meetdata en rapportageperioden blijven ongewijzigd, maar nieuwe SHA-256-sleutels bewaken
dezelfde uniciteit per website en datum. De losse, ongebruikte zoektermindex vervalt. Hiermee daalt
de indexgroei zonder historische data of inhoudelijke berekeningen te wijzigen.

## Begrensde crawlworkerpools

Context: dagelijkse light checks en zware volledige sitecrawls deelden één FIFO-queue. Een lange
volledige crawl kon daardoor kleine controles ophouden en extra containers per job zouden de
NAS-capaciteit onbegrensd maken.

Besluit: RQ routeert light checks, sitemapcontroles en pagina-analyses naar `crawls_light` en
volledige sitecrawls naar `crawls_full`. Compose levert standaard één vaste worker per pool. Een
derde, bewust niet standaard gestarte overflowworker kan beide queues verwerken. De bestaande
database-admission blijft maximaal één actieve crawl per website afdwingen.

Gevolg: beide workloadtypen hebben voorspelbare, begrensde capaciteit zonder een container per job.

## 2026-07-30 — Wijzigingsruis wordt contextueel onderdrukt of als incident gegroepeerd

Context: een schone Schipper-crawl leverde 170 wijzigingsregels op. Daarvan vormden 147 regels één
gemengde hostwissel tussen `schipperkozijnen.nl` en `verantwoordwonen.com`, 22 regels kwamen van
dynamische zoekresultaatpagina's en één hoofdcontentmelding bestond uitsluitend uit actuele
openingsteksten.

Besluit: functionele `/zoeken`- en `/search`-pagina's blijven als URL, snapshot en linkbewijs
bewaard, maar leveren geen reguliere content-, link- of onpagewijzigingen. Tijdsafhankelijke
Nederlandse openingsstatussen worden uitsluitend voor de hoofdcontentvergelijking genormaliseerd;
andere showroominhoud blijft meetellen. Canonical-, schema- en linkwisselingen tussen dezelfde twee
hosts en paden blijven als onderliggende records bewaard, maar worden per crawl als één
websitebrede domeinverwisseling gepresenteerd.

Gevolg: dynamische functionele inhoud verdwijnt uit de betekenisvolle wijzigingshistorie zonder
bereikbaarheidsbewijs te verliezen. Een tenant-, cache- of hostincident blijft volledig
controleerbaar, maar verschijnt niet als tientallen losse URL-gebeurtenissen. Echte wijzigingen in
adressen, pagina-inhoud, canonicals of links buiten deze aantoonbare patronen blijven zichtbaar.

## 2026-07-30 — Taakuitvoering blijft gescheiden van issue-detectie

Context: `issues.status` wordt automatisch door crawls opgelost, geverifieerd en heropend. Menselijke
uitvoering vraagt daarnaast planning, eigenaarschap, wachtstatus, aangepaste URL's, feedback en een
asynchrone verificatie. Beide processen in dezelfde statuskolom zouden elkaars betekenis aantasten.

Besluit: issues blijven de technische diagnosebron. Een gekoppelde taaklaag krijgt een compacte
menselijke workflow en verwijst naar één of meer issues en URL's zonder bewijs te kopiëren.
Verificatiestatus blijft apart van taakstatus. De eerste bibliotheek bevat alleen concrete,
veelvoorkomende en grotendeels controleerbare aanbevelingstypen.

Gevolg: een taak kan uitgevoerd zijn terwijl verificatie nog loopt, en een toekomstige crawl kan
het technische issue blijven oplossen of heropenen zonder menselijke planning te overschrijven.

## 2026-07-30 — Klantoverstijgend leren gebruikt alleen privacyveilige aggregaten

Context: uitvoeringstijd, handmatige correcties en verificatie-uitkomsten kunnen aanbevelingen en
confidence verbeteren, maar ruwe klantdata mag niet tussen tenants lekken en kleine groepen zijn
statistisch en privacytechnisch onbetrouwbaar.

Besluit: feedback blijft eerst klantgebonden. Latere kalibratie gebruikt alleen aggregaten met
minimaal 10 onafhankelijke klanten en 50 beoordeelde taken, een begrensde bijdrage per klant en
onderdrukking van kleine cellen. Ruwe content, URL's, queries, analyticsregels, identiteiten en vrije
opmerkingen worden niet klantoverstijgend gebruikt. Nieuwe kalibratieversies worden offline
geëvalueerd, expliciet goedgekeurd en terugdraaibaar uitgerold.

Gevolg: het systeem kan effort, confidence en verificatieregels verbeteren zonder individuele
klantdata als trainingscorpus te gebruiken. Met de huidige klantomvang wordt alleen instrumentatie
voorbereid; globale kalibratie blijft uitgeschakeld.

## 2026-07-31 — Verificatiescope komt uit bewijs en blijft handmatig corrigeerbaar

Context: een gerichte controle heeft niet alleen een issue-URL nodig, maar betekenisvolle rollen
zoals bron, defect doel of verwacht canonical-doel. Die rollen volledig laten invoeren veroorzaakt
onnodig werk; onbekende doelen automatisch raden maakt de verificatie onbetrouwbaar.

Besluit: vul alleen aantoonbare rollen uit het jongste issuebewijs, de linkgraaf en snapshots.
Gebruik voor defecte links `source` en `broken_target`, voor redirects `source` en
`expected_target`, en voor canonicals `source` en `expected_canonical`. Een bevoegde gebruiker kan
rollen binnen de websitescope toevoegen of verwijderen; iedere correctie wordt gelogd. Niet
aantoonbare gewenste doelen blijven bewust leeg.

Gevolg: bekende crawlgegevens worden hergebruikt, terwijl onzekere intentie niet als feit wordt
opgeslagen. De latere executor kan alleen starten wanneer alle verplichte rollen aanwezig zijn.

## 2026-07-30 — Routineverschuivingen op genummerde archiefpagina's zijn geen wijzigingen

Context: nieuwe publicaties laten content, interne links en ItemList-achtige structured data op
genummerde nieuws-, tag- en andere archiefpagina's doorschuiven. Dit leverde bij AMEC twaalf
wijzigingsrecords op zonder bruikbare vervolgactie.

Besluit: herken uitsluitend expliciete pagineringspaden (`/page/<nummer>` en `/page-<nummer>`) en
de queryparameters `page` en `paged` met een positief nummer. Onderdruk daar vóór opslag alleen
`main_content_changed`, `internal_links_changed` en `structured_data_changed`. Bewaar snapshots en
hashes ongewijzigd. Status, redirect, canonical, robots, indexeerbaarheid, title, description en H1
blijven altijd als wijziging zichtbaar.

Gevolg: verwachte archiefbeweging verdwijnt uit de actielijst, terwijl technische regressies op
pagineringspagina's volledig detecteerbaar blijven. Andere queryparameters en reguliere URL's
vallen bewust buiten de regel.

## 2026-07-31 — Links uit niet-succesvolle foutpagina's zijn geen bronbewijs

Context: een AMEC-404-pagina bevatte zeven navigatie- en ankerlinks uit het fouttemplate die naar
dezelfde ontbrekende route wezen. De linkclassificatie controleerde de 404-status van het doel,
maar niet de status van de bron. Daardoor ontstond een hoog geprioriteerde reparatietaak voor
links die alleen op een foutpagina bestonden.

Besluit: uitsluitend bron-URL's met actuele HTTP-status 200 leveren bewijs voor
`internally_linked_404` en `multiple_broken_internal_links`. Niet-succesvolle bronpagina's blijven
zelf als bereikbaarheidsprobleem zichtbaar, maar hun fouttemplate genereert geen afzonderlijke
linktaak. Een volgende issueherberekening lost eerder aangemaakte foutpositieven automatisch op.

Gevolg: echte defecte links vanaf bereikbare pagina's blijven behouden. Zelfverwijzingen en
navigatielinks uit 404-, 410- en serverfoutpagina's veroorzaken geen dubbele of misleidende actie.

## 2026-07-31 — Gerichte verificatie gebruikt een eigen executor

Context: de bestaande light check verwerkt alle actieve URL's van een website en kan daardoor niet
veilig als controle van één uitgevoerde aanbeveling dienen.

Besluit: iedere verificatie bevriest haar URL-rollen, krijgt een eigen crawltaak en crawlrun en wordt
via een aparte queue uitgevoerd. Een database-index staat per aanbevelingstaak maximaal één actieve
verificatie toe. Alleen noodzakelijke scope-URL's worden opgehaald; full-crawlplanning en
issue-lifecycle worden niet bijgewerkt. De inhoudelijke conclusie staat als `outcome` in het
resultaat, terwijl de bestaande technische verificatiestatus de workerstatus blijft tonen.

Gevolg: aanvragen en retries zijn idempotent, resultaten blijven auditeerbaar en een gerichte
controle kan nooit stilzwijgend uitgroeien tot een volledige websitecrawl.

## 2026-07-31 — Gewenste redirect- en hersteldoelen worden niet geraden

Context: een ontbrekende pagina kan worden hersteld of naar een opvolger worden gestuurd. Een
interne redirect kan een aantoonbaar einddoel hebben, maar de gewenste contentbestemming is niet
altijd uit techniek af te leiden.

Besluit: bewaar crawlbare oude URL's, bronpagina's en aangetoonde einddoelen automatisch. Houd een
nieuwe URL bij herstel optioneel en accepteer zowel rechtstreeks herstel naar HTTP 200 als een
redirect naar een expliciet vastgelegde, bereikbare opvolger. Laat onbekende doelen handmatig via
de beveiligde URL-scope invullen.

Gevolg: de executor kan bereikbaarheid, links en indexatie hard controleren zonder een inhoudelijke
bestemming te verzinnen.

## 2026-07-31 — NAS-staging is terminal-first en volledig geïsoleerd

Context: lokale Docker-belasting hindert ontwikkeling, terwijl de DSM-navigatie onvoldoende
voorspelbaar is voor veilige operationele instructies.

Besluit: bouw een minimale stagingstack op dezelfde NAS, maar met een eigen Compose-project,
volumes, database, secrets en loopbackpoort. Staging bevat standaard geen scheduler of workers en
wordt vanaf de Mac alleen via een SSH-tunnel benaderd. AI Console wordt niet gebruikt. Alle
operationele stappen zijn terminal-first; een onvermijdelijk DSM-klikpad wordt vooraf tegen de
actuele officiële Synology-documentatie geverifieerd.

Gevolg: lokale Docker kan na een succesvolle proefperiode worden uitgefaseerd zonder staging aan
productiedata of publieke toegang te koppelen. De NAS-CPU blijft de begrenzende factor en productie
krijgt voorrang.

## 2026-07-31 — VPS-portabiliteit zonder verdeelde productiestack

Context: de publieke website en SEO Monitor kunnen later naar een Ubuntu-VPS met Plesk en het
domein `thactual.nl` verhuizen, terwijl de NAS beschikbaar blijft voor opslag en testwerk.

Besluit: houd configuratie, services en opslag via environmentvariabelen en Docker-volumes
overdraagbaar. Bij een latere migratie blijven API, database, Redis, scheduler en productieworkers
samen op de VPS. De NAS wordt via een private verbinding uitsluitend gebruikt voor staging,
versleutelde back-ups en hersteltests; productie gebruikt geen databaseverbinding over internet.

Gevolg: een storing van NAS of thuisverbinding legt de publieke productie niet stil. Opslagretentie
en databasegroei moeten vóór de VPS-migratie afzonderlijk worden begrensd en gemonitord.

## 2026-07-31 — Docker-buildcontext bevat geen secrets of runtimegegevens

Context: `Dockerfile` kopieert de buildcontext naar het image. Zonder expliciete uitsluitlijst
kunnen lokale environmentbestanden, exports, back-ups, testresultaten en Git-metadata onderdeel van
het image of de NAS-buildoverdracht worden.

Besluit: gebruik een repositorybrede `.dockerignore`. Sluit alle echte `.env`-varianten en
runtimegegevens uit; alleen de twee lege voorbeeldbestanden blijven beschikbaar als documentatie.

Gevolg: images bevatten geen lokale secrets en builds versturen en verwerken minder gegevens.

## 2026-07-31 — Retentie begint meetbaar en back-upherstel faalt veilig

Context: de productiedatabase is 19 GB. De grootste levende tabellen zijn elementlocaties,
Search Console-querydetails en interne links; databasebloat is niet de primaire oorzaak. De oude
restoreprocedure kon bovendien worden gestart terwijl gespecialiseerde workers nog schreven.

Besluit: breid de read-only retentieaudit uit met leeftijdsbuckets voor interne links, zonder een
verwijderbeleid te activeren. Publiceer een back-up pas nadat `pg_restore --list` slaagt en maak een
SHA-256-bestand. Laat restore checksum en archief controleren en hard weigeren zolang API,
scheduler of een worker draait.

Gevolg: de volgende retentiekeuzes worden op productieaantallen gebaseerd. Een onvolledig archief
of een restore naast actieve schrijvers kan niet meer stilzwijgend worden gebruikt.

## 2026-07-31 — Elementopschoning is per website en per run begrensd

Context: de productieaudit vond ruim 6,2 miljoen aantoonbare opruimkandidaten in
`element_locations`. Eén onbegrensde uitvoering zou te veel databasebelasting en een te groot
operationeel risico geven.

Besluit: behoud de verplichte veilige crawl-drain en vereis operationeel één website-ID per run.
Hanteer standaard maximaal 50.000 verwijderingen, werk in transactiebatches en rapporteer met
`limit_reached` of een vervolguitvoering nodig kan zijn. Een expliciete hogere limiet blijft
technisch begrensd op één miljoen.

Gevolg: opschoning is hervatbaar, meetbaar en gefaseerd uit te rollen. Er wordt pas op productie
verwijderd na een geslaagde stagingproef en een actuele back-up.

## 2026-08-01 — Automatische retentie is persistent en per website geserialiseerd

Probleem: autovacuum maakt verwijderde ruimte herbruikbaar, maar verwijdert geen historische
applicatierijen. Handmatige elementlocatie-cleanup met website-ID's is veilig maar niet duurzaam en
te foutgevoelig bij terminalonderbrekingen.

Besluit: iedere afgeronde volledige crawl maakt idempotent één `retention_operation` aan. De
scheduler zet verschuldigd en onderbroken werk op een afzonderlijke maintenancequeue. De bestaande
integration-worker verwerkt begrensde batches en bewaart na iedere commit voortgang in PostgreSQL.
Cleanup en crawl gebruiken dezelfde websiterijlock; een actieve crawl voor dezelfde website stelt
cleanup uit. Nieuwste crawl- en snapshotbewijs, actieve crawls en issuebewijs blijven beschermd.

Gevolg: onderbroken werk kan zonder dubbele verwijdering worden hervat, een grote website
monopoliseert de worker niet onbeperkt en andere websites blijven beschikbaar. GSC- en
interne-linkretentie blijven afzonderlijke beleidsbesluiten. Migratie `0035` voegt alleen een lege
operatietabel en indexes toe en vereist daarom geen extra productieback-up.
## 2026-08-02 — Releases worden als twee gecontroleerde terminalblokken aangeboden

Context: stapsgewijze bevestiging na checksum, uitpakken, build, migratie en healthchecks maakte
een aantoonbaar geteste release onnodig traag. De stagingrelease van migratie `0036` is succesvol
uitgevoerd met één uploadblok en één NAS-keten.

Besluit: presenteer een vooraf lokaal geteste release standaard in twee blokken. Het eerste blok
streamt het exacte `git archive` vanuit de lokale Mac-terminal. Het tweede blok draait in de al
geopende NAS-shell als één `&&`-keten en bevat checksum, uitpakken, omgevingsspecifieke Compose-
configuratie, build, migratie, herstart, passende wachttijd, status, inhoudelijke controle en
healthcheck. Productie activeert vóór mutaties altijd de veilige crawl-drain.

Gevolg: de keten stopt automatisch bij de eerste fout en vraagt niet na iedere geslaagde stap om
bevestiging. Checks worden niet overgeslagen; ze worden juist in één reproduceerbare releasegang
gebundeld. Workerherstarts gebruiken minimaal `sleep 30`.

## 2026-08-02 — Queuebeleid is versieerbaar en uitval blijft buiten Redis bewaard

Context: RQ bewaart de actuele uitvoering, maar leverde nog geen productbeleid voor queuegrenzen,
websiteprioriteit of duurzaam herstel nadat retries zijn uitgeput. Redis alleen is onvoldoende als
operationeel auditregister.

Besluit: leg één versieerbaar beleid vast met waarschuwing, admissiongrens, retries en time-out per
queue. Een lager prioriteitsgetal gaat voor. Bewaar gekozen queue en prioriteit op de crawljob en
registreer definitieve uitval idempotent in `queue_dead_letters`. De renderqueue blijft zonder
expliciete featureflag en apart Compose-profiel effectief uitgeschakeld totdat begrensde rendering
gecontroleerd wordt geactiveerd.

Gevolg: fase 2 kan backpressure en herstel afdwingen zonder queuegedrag uit losse codeconstanten af
te leiden. Een Redis-reset verwijdert het operationele bewijs van definitieve taakuitval niet.

Implementatie: alle enqueuehelpers gebruiken hetzelfde beleid en weigeren boven de admissiongrens.
Crawls blijven bij capaciteitsgebrek duurzaam wachten; integraties worden in een volgende
schedulercyclus opnieuw aangeboden en interactieve exports of verificaties krijgen een duidelijke
capaciteitsfout. Alleen definitief mislukte jobs komen in het dead-letterregister. Sitemapwerk is
gescheiden van overige light checks, maar gebruikt op de NAS dezelfde begrensde lichte worker.

Operationeel beheer: openstaande dead letters degraderen de systeemstatus en zijn alleen voor de
superuser zichtbaar. Opnieuw aanbieden gebruikt uitsluitend bekende taaktypen en blijvende ID's,
controleert de actuele gekoppelde taak en doorloopt opnieuw de queuegrens. Willekeurige functies of
payloads kunnen niet vanuit het dead-letterrecord worden uitgevoerd.

## 2026-08-02 — Browserrendering is optioneel en verplaatsbaar

Context: Chromium is zwaarder en risicovoller dan een gewone HTTP-crawl. De huidige NAS heeft
beperkte CPU-capaciteit; de gaming-pc is nog geen ingerichte Linux-worker en mag daarom niet als
beschikbare capaciteit worden aangenomen.

Besluit: plaats rendering in een eigen container, queue en Compose-profiel. Begrens iedere taak en
controleer alle browserrequests opnieuw op SSRF. Nieuwe taken vereisen daarnaast expliciet
`RENDERING_ENABLED=true`. Houd het uitvoercontract vrij van NAS-specifieke paden, zodat dezelfde
container later na afzonderlijke infrastructuurgoedkeuring op de Linux-worker kan draaien.

Gevolg: normale crawls en de API krijgen geen browserdependency of browserbelasting. Een eerste
NAS-proef kan klein blijven en latere verplaatsing naar de gaming-pc vereist geen herschrijving van
de analyse- of databaselogica.

## 2026-08-04 — Performancebewijs wordt extern, begrensd en genormaliseerd opgeslagen

Context: lokaal Lighthouse draaien belast de beperkte Mac en NAS, terwijl volledige PageSpeed-
responses omvangrijk zijn en categoriescores zonder oorzaakinformatie geen bruikbare actie vormen.

Besluit: gebruik later de PageSpeed Insights API voor een risicogestuurde selectie van maximaal
tien URL's per batch. Bewaar labdata, CrUX-velddata en auditbewijs herkenbaar gescheiden en sla geen
volledige providerresponse op. De integratie staat standaard uit en vereist een afzonderlijke
featureflag en API-key. Scores alleen maken geen issue.

Gevolg: migratie `0041` is additief en introduceert alleen lege historische observatietabellen en
indexes. De externe client gebruikt een eigen begrensde queue op de bestaande integration-worker,
slaat deelresultaten per URL op en slaat recente successen bij retries over. Issuegroepering volgt
de bestaande lifecycle: alleen concrete mislukte audits worden acties en een gedeelde audit plus
resource wordt als template- of componentoorzaak gegroepeerd. Scores alleen blijven bewijs en
maken geen issue. Rendering en de niet-operationele Linux-worker blijven buiten deze route; de
featureflag blijft uit tot de integrale stagingvalidatie.

## 2026-08-04 — Structured data wordt alleen binnen aantoonbare paginacontext gevalideerd

Context: generiek eisen dat ieder schematype of aanbevolen veld overal aanwezig is veroorzaakt
ruis. Geneste `Organization`-, `Offer`- of `Place`-objecten bewijzen bovendien niet dat de pagina
zelf zo'n paginatype vertegenwoordigt.

Besluit: valideer alleen ondersteunde top-level of `@graph`-typen en controleer per type een kleine
set noodzakelijke velden, primaire zichtbare naam en bekende interne afbeeldingen. Registreer
interne schema-afbeeldingen via het bestaande veilige URL-register. Meld bereikbaarheid alleen na
een echte crawlerstatus en behandel zichtbare-contentverschillen als review.

Gevolg: Product, Article, Organization, LocalBusiness, Event en VideoObject krijgen uitlegbare,
dedupliceerbare acties zonder algemene ontbrekend-schemawaarschuwingen of extra externe fetches.

## 2026-08-04 — Sitemapkwaliteit wordt apart van URL-status beoordeeld

Context: de import sloeg bruikbare sitemap-URL's op en signaleerde status- en redirectproblemen,
maar ongeldige `loc`- of `lastmod`-waarden, duplicaten en foutieve robotsdeclaraties verdwenen uit
beeld. Een geconfigureerde websitevreemde sitemaproot kon bovendien onnodig worden opgehaald.

Besluit: verzamel documentkwaliteit tijdens de bestaande begrensde import en maak twee gegroepeerde
website-issues: één voor sitemapinhoud en één voor sitemapdeclaraties in robots.txt. Gebruik alleen
absolute HTTP(S)-roots binnen de ingestelde websitescope als fetchdoel en bewaar hoogstens tien
voorbeelden per bevindingstype.

Gevolg: de sitemapgenerator en robotsconfiguratie krijgen concrete, dedupliceerbare acties zonder
extra netwerkronde, database-migration of generieke kwaliteitsscore. Een volgende schone import
lost het issue via de bestaande lifecycle op.

## 2026-08-04 — In-app taakmeldingen scheiden gebeurtenis en leesstatus

Context: taak- en verificatiehistorie was persistent, maar alleen vanuit een geopend issuedetail
bereikbaar. Een globale melding direct als gelezen of ongelezen opslaan zou de status van alle
gebruikers binnen dezelfde klant beïnvloeden.

Besluit: bewaar de websitegebonden melding één keer en leg leesstatus in een afzonderlijk record
per gebruiker vast. Gebruik dezelfde tenantautorisatie als taakroutes. API-keyverkeer mag lezen,
maar niet namens een gebruiker afvinken. E-mail en externe kanalen blijven buiten deze release.

Gevolg: taak- en verificatiewerk blijft zichtbaar nadat een browser is gesloten, zonder gedeelde
leesstatus tussen gebruikers of tenants. Migration `0042` voegt tabellen toe en verruimt alleen de
rollenconstraint; bestaande taakdata wordt niet herschreven.

## 2026-08-07 — Kansen en leadconclusies vereisen uitlegbaar en betrouwbaar bewijs

Context: gecombineerde totaalscores, generieke conversietellers en opvallende eventpieken kunnen
een overtuigende maar onjuiste groeikans of leadconclusie opleveren.

Besluit: score kansen alleen vanuit versieerbare deelscores en benoemde bijdragers. Gebruik voor
leadvergelijkingen precies één primaire analyticsbron. GA4 telt uitsluitend expliciet gekozen
gekwalificeerde events; Matomo gebruikt uitsluitend eigen conversies en bezoeken. Bewaar sterke
event-/sessie- of conversie-/bezoekafwijkingen ongewijzigd als brondata, maar verlaag confidence,
toon een gevoeligheidsberekening en onderdruk conclusies zolang de gekozen meetperiode de sterke
afwijking bevat. Geef het label `betrouwbaar` pas na twee schone controles.

Gevolg: opportunity- en assistentuitkomsten blijven herleidbaar, tenantgebonden en read-only.
Meetproblemen worden normale gededupliceerde issues met bewijs en verificatiehistorie, zonder GA4
en Matomo te combineren of een algemene SEO-score te introduceren.

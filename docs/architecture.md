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

## Issue lifecycle

Na opslag vergelijkt de analyse-engine een snapshot met zijn voorganger en schrijft afzonderlijke
`changes`. Technische controles leveren signalen die op website, URL en type worden gededupliceerd.
Verdwenen signalen worden `resolved`, een volgende schone controle kan ze `verified` maken en een
terugkerend signaal opent hetzelfde issue opnieuw. `issue_occurrences` bewaart bewijs per crawl.

## Jobs en exports

De API en scheduler schrijven eerst een persistent `crawl_job` en plaatsen daarna alleen het ID op
de RQ-queue. De worker voorkomt gelijktijdige crawls per website en bewaart deelresultaten per URL.
RQ verzorgt retries met oplopende wachttijd. CSV-exporten leveren één dataset; Excel bevat metadata
en aparte tabbladen voor URL's, issues, wijzigingen, interne links en vacatures. Het vacaturetabblad
bevat lifecycle, Google for Jobs-status, datums, sollicitatiegegevens, interne links en actieve
bevindingen, maar geen technische database-ID's. Bestanden staan in een gedeeld volume.

## Crawl-diepte

Een volledige sitecrawl start op de genormaliseerde basis-URL met diepte 0 en verwerkt interne
links breadth-first. Nieuw ontdekte URL's worden binnen dezelfde crawl ingepland. De kortste
gevonden afstand vanaf de basis-URL wordt als `urls.crawl_depth` opgeslagen. URL's die alleen uit
een sitemap of eerdere crawl bekend zijn en niet intern bereikbaar zijn, houden een lege diepte.

Na de breadth-first crawl worden actieve sitemap-URL's met een lege diepte als orphan page
gemarkeerd. Het issue wordt per URL gededupliceerd en automatisch opgelost zodra de URL bij een
latere crawl wel intern bereikbaar wordt.

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

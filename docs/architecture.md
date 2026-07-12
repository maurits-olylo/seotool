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
en aparte tabbladen voor URL's, issues, wijzigingen en links. Bestanden staan in een gedeeld volume.

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
Afbeeldingen en documenten krijgen een lichte HEAD-controle. Grote afbeeldingen (meer dan 2 MB) en
documenten (meer dan 5 MB) leveren afzonderlijke issues op zonder de volledige bestanden te downloaden.

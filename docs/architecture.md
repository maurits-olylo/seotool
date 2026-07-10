# Architectuur

De API verwerkt klanten, websites en instellingen. SQLAlchemy-modellen vormen de enige toegang
tot PostgreSQL; schemawijzigingen lopen uitsluitend via Alembic. Redis/RQ scheidt crawltaken van
HTTP-verzoeken. De scheduler wordt in fase 5 verantwoordelijk voor periodieke jobs.

Alle database-ID's zijn UUID's en tijdstempels worden in UTC opgeslagen. Crawler-, snapshot-,
wijzigings- en issuecomponenten blijven onderling gescheiden.

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

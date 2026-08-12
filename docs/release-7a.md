# Release 7a — Privacy- en beveiligingsgate

## Release 7a-A — Identiteit en toegang

Status: afgerond en op 5 augustus 2026 met releasecommit `b537c78` op staging en productie
gevalideerd.

Deze eerste deelrelease sluit de kritieke account- en tenanttoegangsrisico's uit de audit van
3 augustus 2026:

- uitnodigingen kunnen het wachtwoord van een bestaand account niet vervangen;
- schrijfrechten worden afgedwongen op de rol binnen de betreffende tenant;
- sessies zijn server-side, intrekbaar en worden ingetrokken bij uitloggen, rolwijziging en
  toegangsverwijdering;
- beheerder- en superusersessies verlopen na twee uur; gewone gebruikerssessies na twaalf uur;
- OAuth-state is eenmalig en gebonden aan gebruiker, sessie, tenant en provider;
- login-rate-limiting, request-origincontrole en MFA voor beheerders zijn aanwezig;
- MFA ondersteunt TOTP en eenmalige herstelcodes; mislukte MFA-pogingen vallen onder de rate-limit;
- tenantbeheerders kunnen geen andere beheerder creëren en de laatste tenantbeheerder blijft
  beschermd;
- login, MFA, uitnodigingen en toegangswijzigingen komen zonder secrets of bronadres in een
  afzonderlijk beveiligingsauditregister;
- de algemene technische API-key wordt in productie altijd geweigerd. De huidige workers gebruiken
  geen HTTP-API-key en werken rechtstreeks via hun database- en queueverbinding.

De release bevat migraties `0046` tot en met `0051`. Migratie `0046` trekt bestaande openstaande
uitnodigingen preventief in; de overige migraties zijn additief. Maak daarom vóór deployment een
geverifieerde databaseback-up en controleer na migratie expliciet dat Alembic `0051` meldt.

Voor productie moet `MFA_ENFORCEMENT_ENABLED=true` actief zijn. `API_KEY` blijft leeg en kan geen
productietoegang geven. De API blijft uitsluitend via de bestaande loopbackbinding en HTTPS-reverse
proxy bereikbaar.

Lokale acceptatie:

- Ruff: geslaagd;
- volledige testsuite: 428 tests geslaagd;
- Alembic: één head, `0051`;
- JavaScript-rendering en PageSpeed blijven uitgeschakeld;
- de Linux-worker blijft buiten deze release.

De acceptatie omvat staging, gecontroleerde deployment en functionele verificatie van persoonlijk
inloggen, verplichte MFA, sessie-intrekking, tenantrollen, OAuth-state en auditregistratie.

Stagingacceptatie bevestigde migratie `0051`, een gezonde API en database, actieve
MFA-handhaving, lokale encryptie van het TOTP-secret, een scanbare lokaal gegenereerde QR-code,
succesvolle activatie, opnieuw inloggen met MFA en de tweeuursgrens voor een nieuwe
superusersessie. Staging is daarmee functioneel volledig akkoord. De algemene technische API-key
blijft in productie uitgeschakeld. De loginpresentatie wordt later als interfacepolish opgesplitst
in een afzonderlijke wachtwoordstap en verificatiestap; dit verandert de reeds werkende
authenticatie niet.

De productiedeployment is uitgevoerd vanaf de exacte releasecommit na een veilige crawl-drain en
een inhoudelijk geverifieerde databaseback-up. Productie is gezond op migratie `0051`; de API is
uitsluitend op loopback gepubliceerd, MFA-handhaving en de tweeuursgrens voor beheerders zijn
actief en de algemene technische API-key wordt geweigerd. Activeren via de QR-code, uitloggen en
opnieuw inloggen met MFA zijn functioneel bevestigd. De crawl-drain is na alle controles zonder
wachtende taken opgeheven.

## Release 7a-B — Platform en privacy

Status: technisch grotendeels afgerond en gedeployed. De actuele herstelmatrix en resterende
securitygates staan in `docs/security-remediation-status-2026-08-11.md`.

Deze deelrelease behandelt de resterende platformhardening, SSRF-/netwerkisolatie, secretscheiding,
containerbeleid, back-upbewijs, supply-chaincontroles en de functionele privacygate.

### Fase 1 — DNS-rebindingbescherming voor de HTTP-crawler

De gewone HTTP-crawler verbindt nu uitsluitend met het IP-adres dat direct voorafgaand aan de
aanvraag is opgelost en als publiek is gevalideerd. De oorspronkelijke domeinnaam blijft behouden
voor de HTTP-hostheader en TLS-SNI/certificaatcontrole. Iedere redirect wordt opnieuw logisch
opgebouwd, opgelost, gevalideerd en op een afzonderlijke verbinding uitgevoerd. Gemengde
publieke/private DNS-antwoorden, URL-credentials en niet-standaard HTTP-poorten worden geweigerd.
Proxy-instellingen uit de hostomgeving worden niet overgenomen.

Lokale acceptatie:

- Ruff: geslaagd;
- volledige testsuite: 433 tests geslaagd;
- regressietests bevestigen IP-pinning, behoud van host en TLS-SNI, private en gemengde
  DNS-blokkering en veilige redirects;
- JavaScript-rendering blijft uitgeschakeld en valt buiten deze fase;
- er zijn geen databasewijzigingen of migraties.

### Fase 2 — Containerhardening

Status: lokaal afgerond en nog niet gedeployed.

Alle applicatiecontainers gebruiken een vaste niet-rootgebruiker met UID/GID `10001`. Hun
rootfilesystem is alleen-lezen, alle Linux-capabilities zijn verwijderd en privilegeverhoging is
uitgeschakeld. Alleen `/tmp` en de minimaal noodzakelijke exportvolume zijn schrijfbaar. Daarnaast
gelden per container grenzen voor processen, geheugen en relatieve CPU-prioriteit, afgestemd op de
beperkte productiecapaciteit van de NAS. PostgreSQL en Redis behouden bewust het officiële
imagebeleid; hun opstartrechten worden niet zonder afzonderlijke migratie- en herstelproef
gewijzigd.

Bij de eerste staging- en productiedeployment moet de bestaande exportvolume vóór het starten van
de niet-root applicaties eenmalig en gecontroleerd aan UID/GID `10001` worden overgedragen. Dit
wijzigt geen exportinhoud en vereist geen databasemigratie of databaseback-up. De renderer blijft
uitgeschakeld.

Lokale acceptatie:

- productie- en staging-Composeconfiguratie: geldig;
- Ruff: geslaagd;
- volledige testsuite: 436 tests geslaagd;
- regressietests bewaken het niet-rootimage, alleen-lezen filesystems, capability-drop,
  privilegeblokkering en proces- en resourcegrenzen;
- een zware lokale imagebuild is volgens het infrastructuurprofiel overgeslagen en wordt op staging
  uitgevoerd.

### Fase 3 — Secretscheiding en veilige productiestart

Status: lokaal afgerond en nog niet gedeployed.

Compose injecteert niet langer het volledige environmentbestand in iedere applicatiecontainer.
De API ontvangt uitsluitend zijn authenticatie-, OAuth- en bootstrapconfiguratie; de
integration-worker ontvangt alleen de OAuth-, tokenencryptie- en optionele PageSpeedconfiguratie
die voor integraties nodig is. Crawl-, export-, render- en schedulerprocessen krijgen deze
gevoelige waarden niet. Alle services behouden vooralsnog de bestaande database- en Redisverbinding;
afzonderlijke databaseaccounts en grants vereisen een aparte, gecontroleerde rechtenmigratie.

De productieconfiguratie stopt nu direct bij bekende standaarddatabasecredentials, uitgeschakelde
API-MFA of een ontbrekende/ongeldige tokenencryptiesleutel voor de API en integration-worker. De
voorbeeldconfiguratie bevat geen actieve technische API-key of standaard databasewachtwoord meer.
Productie- en staging-environmentbestanden blijven buiten Git, krijgen modus `0600` en worden niet
in logs getoond.

Lokale acceptatie:

- productie- en staging-Composeconfiguratie: geldig;
- Ruff: geslaagd;
- volledige testsuite: 438 tests geslaagd;
- regressietests bewaken servicegebonden secretinjectie en fail-fast productieconfiguratie;
- er zijn geen databasewijzigingen of migraties.

### Stagingacceptatie fasen 1–3

De gecombineerde stagingdeployment vanaf commit `214a08d` is technisch en functioneel akkoord.
De API draait gezond op migratie `0051`, als niet-rootgebruiker `app`, met een alleen-lezen
rootfilesystem, alle capabilities verwijderd en `no-new-privileges` actief. Login en MFA werken;
de beschikbare testklant en interface laden zonder fout of laadlus. Staging bevat geen verdere
klanten, websites of URL-details, waardoor die inhoud in deze acceptatie niet functioneel kon
worden beoordeeld.

De Synology-kernel ondersteunt de ingestelde Docker-PID-limiet niet en Docker negeert uitsluitend
die limiet met een expliciete waarschuwing. De overige containerbeperkingen zijn aantoonbaar actief.
Deze platformbeperking blijft open voor aanvullende compensatie of een toekomstige
uitvoeringsomgeving met volledige cgroupondersteuning. JavaScript-rendering en PageSpeed blijven
uitgeschakeld.

### Productieacceptatie fasen 1–3

De gecombineerde productiedeployment vanaf commit `6f93f06` is technisch en functioneel akkoord.
Alle actieve applicatieservices draaien gezond op migratie `0051`, als niet-rootgebruiker, met een
alleen-lezen rootfilesystem, capability-drop, `no-new-privileges` en aantoonbare secretscheiding.
De veilige crawl-drain is zonder achterblijvende of hervatte taken opgeheven. De Synology-waarschuwing
over de niet-ondersteunde PID-limiet is gelijk aan staging; alle overige containerbeperkingen zijn
actief.

Persoonlijk inloggen met MFA, klanten, websites, URL-details, dashboard, inzichten en integraties
zijn functioneel gecontroleerd. De GSC- en GA-koppeling voor één productieklant moest opnieuw worden
geactiveerd; beide koppelingen werken weer en de daaropvolgende historische import is succesvol
afgerond. JavaScript-rendering en PageSpeed blijven uitgeschakeld. Fasen 1–3 zijn hiermee op
productie afgerond; de resterende platform-, back-up-, supply-chain- en privacyonderdelen van
Release 7a-B blijven open.

### Fase 4 — Database-identiteiten en minimale rechten

Status: afgerond en op 6 augustus 2026 lokaal, op staging en op productie technisch en functioneel
geaccepteerd.

API, crawler, integraties, exports en scheduler gebruiken afzonderlijke PostgreSQL-loginrollen.
Een herhaalbaar configuratiescript maakt of roteert deze rollen en herstelt hun grants naar het
vastgelegde beleid. Alleen de migratiebeheerder bezit schemaobjecten en voert Alembic uit.
Runtime-rollen kunnen geen schemaobjecten maken. Crawl-, export- en schedulerrollen hebben geen
toegang tot account-, sessie-, OAuth-state- of security-audittabellen. De exportrol kan alleen het
eigen exportrecord wijzigen. Nieuwe tabellen krijgen niet automatisch workerrechten en moeten bij
een volgende migration bewust aan het rechtenbeleid worden toegevoegd.

Er is geen Alembic-migratie: PostgreSQL-rollen zijn omgevingsconfiguratie en geen onderdeel van het
applicatieschema. Staging moet positieve serviceflows en negatieve grants bevestigen voordat
dezelfde rolconfiguratie in productie wordt toegepast.

Staging bevestigde afzonderlijke logins, een gezonde API-databaseverbinding en de verwachte
positieve en negatieve tabelrechten. Persoonlijk inloggen met MFA, klant- en websiteoverzicht,
navigatie zonder laadlus en uitloggen zijn functioneel geslaagd. Environmentwachtwoorden worden
voortaan uitsluitend met de niet-tonende, atomische configuratiehelper toegevoegd of geroteerd.

Productie draait gezond met afzonderlijke rollen voor API, crawler, integraties, exports en
scheduler. De rechtenmatrix bevestigde dat runtimeprocessen hun noodzakelijke tabellen wel en
account-, sessie-, OAuth-state- en security-audittabellen niet buiten hun taak kunnen benaderen.
Alle actieve services zijn gezond, de API-databaseverbinding meldt `ok` en migratie `0051` bleef
ongewijzigd. De veilige crawl-drain is na de controles opgeheven zonder gepauzeerde taken te
hervatten. Persoonlijk inloggen met MFA, klanten, websites, URL-details, dashboard, inzichten,
integraties, uitloggen en opnieuw inloggen zijn functioneel geslaagd. Er is geen crawl of
historische integratie-import uitsluitend voor releasecontrole gestart.

### Fase 5 — Crawlernetwerkisolatie

Status: productie geaccepteerd op 6 augustus 2026.

PostgreSQL en Redis staan met alle applicatieservices op een intern backendnetwerk zonder directe
uitgaande route. Alleen API en integration-worker krijgen daarnaast het algemene applicatie-
egressnetwerk. Crawlworkers en de uitgeschakelde renderer krijgen uitsluitend een afzonderlijk
crawler-egressnetwerk. Docker-IPv6 staat voor alle nieuwe netwerken expliciet uit.

Een idempotente hostfirewall koppelt het dynamisch gevonden crawler-egresssubnet vóór de standaard
terugkeerregel aan `DOCKER-USER`. Uitgaand crawlerverkeer naar localhost, private, link-local,
metadata-, test-, multicast- en gereserveerde IPv4-ranges wordt geweigerd; publiek IPv4-verkeer
blijft mogelijk. DNS is alleen toegestaan via TCP/UDP-poort 53 naar de IPv4-resolvers van de host.
De bestaande IP-validatie en IP-pinning blijven als onafhankelijke applicatielaag actief.

Staging en productie bevestigden gescheiden interne, applicatie-egress- en crawler-egressnetwerken
met uitgeschakeld Docker-IPv6. DNS en publiek crawlerverkeer waren bereikbaar, terwijl een directe
verbinding met het metadata- en link-localbereik werd geblokkeerd. Beide firewallketens bleven
gelijktijdig actief en alle productiecontainers, API- en databasehealthchecks waren gezond. De
veilige crawl-drain is na de controles opgeheven zonder taken te hervatten; er is geen crawl of
import voor de releasecontrole gestart. Login met MFA, klanten, websites, analyse, acties en
uitloggen zijn functioneel geslaagd.

DSM 7 bevat een ingeschakelde, door `root` uitgevoerde `Boot-up`-taak die de begrensd herhalende
firewallhersteller vanaf de gedeelde projectmap uitvoert. Een handmatige uitvoering bevestigde dat
zowel de productie- als stagingketen actief wordt hersteld. Een daadwerkelijke NAS-herstart is niet
uitsluitend voor deze releasecontrole uitgevoerd en blijft onderdeel van gepland onderhoud.

### Fase 6A — Versleuteld lokaal herstelbaar fundament

Status: volledig geaccepteerd op lokaal, staging en productie, inclusief operationele planning en
waarschuwing bij mislukking.

De bestaande losse PostgreSQL-dump wordt vervangen door één cliënt-side versleuteld herstelpakket
met database, duurzaam exportvolume, noodzakelijke herstelconfiguratie, exacte Git-commit, manifest
en verplichte checksums. Back-up en restore weigeren ontbrekende sleutels, onveilige sleutel- of
environmentrechten, ontbrekende checksums, beschadigde archieven en restore naast schrijvende
services. Een afzonderlijke controle meldt een te oud, onleesbaar of niet-ontsleutelbaar pakket.

De herstelsleutel wordt niet in Git, het project, het back-upvolume of logs bewaard. Een afzonderlijk
privacyvolume registreert verwijderde klant- en website-UUID's zonder persoonsgegevens. Restore past
dit actuelere register idempotent toe voordat schrijvers opnieuw mogen starten, zodat een ouder
databasepunt verwijderde gegevens niet opnieuw activeert. De lokale acceptatie omvat regressietests
en een volledige synthetische stagingrestore. Voorlopige doelen zijn RPO 24 uur en RTO 4 uur; de
stagingmeting wordt leidend.

Stagingacceptatie op 6 augustus 2026 bevestigde vanaf commit `f790032` een volledig versleuteld
pakket met leesbare PostgreSQL-dump, exports, herstelconfiguratie, privacyregister, manifest en alle
verplichte checksums. De geïsoleerde restore zette de synthetische database en het exportbewijs
terug, terwijl een klant die ná het back-upmoment was verwijderd door het actuelere onafhankelijke
privacyregister opnieuw werd verwijderd. Het gereedsignaal meldde
`full_restore_proof=passed privacy_reactivation=blocked exports_readable=true`. API, PostgreSQL en
Redis waren daarna gezond en Alembic bleef op `0051`. De proef startte geen crawl of import en
gebruikte geen productiedata.

De eerste restorepoging stopte na database- en privacyherstel veilig op onvoldoende leesrechten voor
het tijdelijke exportarchief. Commit `f790032` maakt uitsluitend `exports.tar` leesbaar voor de
niet-root herstelcontainer en mount alleen dat bestand. De hervatte exportrestore en alle
eindcontroles slaagden. De Synology-kernelwaarschuwing over de niet-ondersteunde PID-limiet bleef
ongewijzigd; een Compose-waarschuwing over het vooraf aangemaakte stagingprivacyvolume had geen
functionele impact.

De productieacceptatie op 6 augustus 2026 eindigde gezond op commit `df1b907`. De API gebruikt het
vaste externe privacyvolume met schrijfbare UID/GID `10001`; het oude automatisch benoemde volume
is niet verwijderd. De volledige productieback-up kon alleen worden gepubliceerd nadat database,
exports, herstelconfiguratie, privacyregister, manifest, encryptie en alle checksums leesbaar waren.
Integration-worker, export-worker en scheduler zijn daarna gezond hervat. API, PostgreSQL, Redis en
beide crawlerpools bleven gezond, Alembic bleef op `0051` en de crawl-drain eindigde met
`active=false resumed=0`. Er is geen productierestore, crawl of historische import gestart.

Twee eerdere productiecontroles stopten vóór de back-up: eerst gebruikte de API nog een oud
root-owned Compose-volume, daarna bleek de vaste volumenaam niet expliciet extern. De uiteindelijke
configuratie forceerde uitsluitend de API opnieuw met het vooraf bevoegde externe volume. De oude
volumes zijn bewust niet als verkennende stap verwijderd.

De definitieve operationele acceptatie volgde op commit `883ea5e`. De ingeschakelde DSM-roottaak
`SEO Monitor encrypted backup` voert de gecontroleerde wrapper dagelijks om 03:00 uit en meldt
abnormale beëindiging per e-mail. De handmatige taakrun van 6 augustus 2026 duurde van 23:07:22 tot
23:15:03 en eindigde met `Normal (0)`. De oude database-only taak is uitgeschakeld en mag worden
verwijderd, zodat geen overlappende back-ups op hetzelfde tijdstip kunnen ontstaan. Daarmee is fase
6A volledig afgerond; de beperking van SEC-13 resteert uitsluitend in fase 6B.

### Fase 6B — Onafhankelijke immutable EU-back-up

Status: bewust geparkeerd als harde gate vóór de Friends & Family-release.

Deze fase kiest en configureert pas dan een betaalde tweede EU-opslaglocatie, Object Lock of
gelijkwaardige verwijderbescherming, automatische lifecycle en herstel vanaf uitsluitend de
onafhankelijke kopie. SEC-13 blijft tot die acceptatie gedeeltelijk open en kan vóór Friends &
Family niet als volledig opgelost worden aangemerkt.

### Fase 7A — Gehashte productiedependencies

Status: lokaal en op staging geaccepteerd; productiebuildvalidatie blijft open.

- `requirements.lock` bevat de volledige runtimegraaf met exacte versies en packagehashes;
- de renderimage gebruikt dezelfde runtime-lock en een kleine gehashte Playwright-overlay;
- beide applicatie-images installeren met `--require-hashes` en lossen tijdens de build geen brede
  versieranges uit `pyproject.toml` meer op;
- de applicatiecode draait rechtstreeks vanuit `/app`, waardoor geen tweede onbeheerde
  build-isolationstap nodig is;
- regressietests bewaken dat Dockerfiles niet terugvallen op een ongehashte projectinstallatie.

Deze fase sluit SEC-15 nog niet. Een gecontroleerde Python 3.12-build, ontwikkel-/testlock, CI,
SBOM en dependency-, secret-, SAST- en imagescans volgen in fase 7B.

Stagingacceptatie op 11 augustus 2026:

- API, render-worker, PostgreSQL en Redis waren gezond na de gehashte rebuild;
- Alembic bleef zonder schemawijziging op één head `0064`;
- `pip check` meldde in beide applicatie-images geen gebroken requirements;
- de API draaide met de vastgezette FastAPI- en SQLAlchemy-versies;
- de render-worker importeerde Playwright en bleef als RQ-worker geregistreerd;
- de API-healthcheck bleef `ok`;
- definitief gereedsignaal: `supply-chain-7a-staging-ok`.

De waarschuwingen over niet-schrijfbare pip-cachemappen zijn verwacht bij de bewust niet-root en
read-only draaiende containers en hebben geen functionele of beveiligingsimpact.

### Fase 7B — CI, SBOM en geautomatiseerde scans

Status: CI-techniek op GitHub geaccepteerd; de releasegate blokkeert inhoudelijk op bekende
dependency- en containerbevindingen waarvoor nog geen volledig installeerbare oplossing bestaat.

- Python 3.12 gebruikt één gehashte CI-lock voor tests, linting en securitytools;
- de workflow heeft alleen leesrecht, gebruikt geen `pull_request_target` en pint alle externe
  Actions op volledige commit-SHA;
- iedere push en pull request draait Ruff, de volledige testsuite, Bandit, een productiegerichte
  secretscan en `pip-audit` tegen de runtime-lock;
- iedere run maakt een reproduceerbare CycloneDX-SBOM en bewaart die dertig dagen als artifact;
- beide Dockerimages worden opnieuw gebouwd en met een vastgepinde Trivy-release op kritieke en
  hoge kwetsbaarheden gecontroleerd;
- de Trivy-pin gebruikt de geverifieerde immutable release `v0.36.0`; veranderlijke tags zijn niet
  toegestaan.

De lokale dependency-audit vond vier advisories in `cryptography 46.0.7`. De lock is verhoogd naar
de hoogst leverbare versie `48.0.1`, waarmee één advisory is opgelost. Drie advisories noemen
versie 49 of 50 als fix, maar die versies zijn nog niet beschikbaar voor de Python 3.12-resolver.
Zij worden niet genegeerd: de CI blijft rood totdat een installeerbare veilige versie bestaat of
een afzonderlijke expliciete en tijdgebonden risicoacceptatie is goedgekeurd.

### Fase 7C — Eerste gecontroleerde GitHub-run

Status: CI-bewijs geaccepteerd; securitygate blijft rood.

GitHub-run `31562107226` op commit `f224a6f` bewees op 12 augustus 2026 dat:

- de gehashte Python 3.12-installatie en `pip check` slagen;
- de volledige suite van 628 tests, Ruff, Bandit en de productiegerichte secretscan slagen;
- een reproduceerbare CycloneDX-SBOM wordt gemaakt en als artifact bewaard;
- beide applicatie-images worden gebouwd en onafhankelijk door Trivy worden gescand;
- de afsluitende containergate rood blijft zodra een van beide scans faalt;
- `pip-audit` de drie open advisories in `cryptography 48.0.1` blokkerend rapporteert;
- Trivy voor de API-image 23 hoge/kritieke OS-bevindingen en twee Python-bevindingen meldt;
- Trivy voor de rendererimage twee hoge OS-bevindingen en twee Python-bevindingen meldt.

De workflow is daarmee functioneel geaccepteerd, maar deze releasefase is beveiligingsinhoudelijk
niet vrijgegeven. Eerst moeten nieuwe veilige basisimages en cryptography-releases beschikbaar en
opnieuw gelockt, gebouwd en gescand zijn, of moet voor iedere resterende bevinding afzonderlijk een
expliciete, gemotiveerde en tijdgebonden risicoacceptatie worden vastgelegd.

### Fase 7D — Immutable basisimages en updateproef

Status: gedeeltelijk opgelost; staging en productie nog niet bijgewerkt.

- De API-basis is vastgezet op de exacte Python `3.12.13-slim-trixie`-manifestdigest.
- De tijdelijke Playwrightproef met Ubuntu 26.04 vergrootte de OS-set van twee naar zeven hoge
  bevindingen en is daarom niet behouden.
- De renderer blijft op Playwright `1.61.0-noble`, maar is nu eveneens op een exacte
  multi-architecture manifestdigest vastgezet.
- De Node-buildstage voor axe-core is op een exacte officiële manifestdigest vastgezet.
- GitHub-run `31562595012` bewees dat beide nieuwe images bouwen en dat de onverhelpbare
  bevindingen nog steeds blokkerend worden gerapporteerd.

De actuele distributierepositories leveren nog geen fixes voor de gemelde OS-pakketten. Ook
cryptography 49/50 is nog niet installeerbaar. Daarom wordt geen betekenisloze package-upgrade,
scanuitzondering of bredere risicoacceptatie toegevoegd.

### Fase 7E — Automatische update- en CVE-signalering

Status: lokaal geïmplementeerd; eerste geplande GitHub-cyclus blijft open.

- Dependabot controleert wekelijks Python-packages, Dockerbasisimages en GitHub Actions.
- Samenhangende updates worden per ecosysteem gegroepeerd en als reviewbare pull request aangeboden.
- Er is geen automatische merge, release of deployment ingericht.
- De volledige securityworkflow draait daarnaast iedere maandag om 04:15 UTC en kan handmatig
  worden gestart.
- Daardoor worden nieuwe advisories en databasewijzigingen ook zonder repositorywijziging opnieuw
  tegen beide images en de runtime-lock getoetst.
- Iedere update blijft onderworpen aan hashes, tests, SBOM, SAST, secretscan en beide Trivy-gates.

### Fase 7F — Securitydetectie en incidentregister

Status: geïmplementeerd en op staging geaccepteerd op 12 augustus 2026.

- Bestaande audit-events worden automatisch beoordeeld op herhaalde login- en MFA-fouten en op
  promotie naar een beheerdersrol.
- Detectie maakt één idempotent, duurzaam incident per regel, bron en dag en heropent een opgelost
  incident wanneer hetzelfde patroon terugkomt.
- Alleen de superuser kan incidenten opvragen, herdetectie starten of met een concrete toelichting
  afsluiten.
- Open incidenten degraderen de operationele systeemstatus.
- Bewijs bevat uitsluitend regelmetadata, hashes en interne identifiers; geen wachtwoorden, tokens,
  adressen of klantpayloads.
- `scripts/accept-release-7f-staging.py` bewijst detectie, drempel, idempotentie, afhandeling en
  fixturecleanup.
- Staging draaide migratie `0065` als enige head en bevestigde vijf gebeurtenissen als één
  opgelost incident, een schone fixturecleanup en een gezonde API/database.

Externe, wijzigingsbeschermde EU-opslag en een gekozen notificatiekanaal blijven noodzakelijk om
SEC-14 volledig te sluiten. Deze fase introduceert daarvoor niet stilzwijgend een leverancier.

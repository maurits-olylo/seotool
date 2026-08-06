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

Status: in uitvoering; fase 1 is lokaal afgerond en nog niet gedeployed.

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

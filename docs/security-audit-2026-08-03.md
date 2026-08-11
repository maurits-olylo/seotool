# Security-audit SEO Monitor

**Datum:** 3 augustus 2026  
**Scope:** beschikbare broncode en repositoryconfiguratie in `/Users/bibivanlijden/Documents/SEO Tool`  
**Methode:** read-only code- en configuratiebeoordeling, gerichte statische controles en beperkte lokale verificatie  
**Normenkader:** OWASP ASVS niveau 2 als beoogde baseline

## Managementsamenvatting

**Besluit: NO-GO voor professioneel multi-tenant productiegebruik in de huidige staat.**

De code bevat twee direct exploiteerbare autorisatieproblemen met potentieel kritieke impact: een uitnodigingsflow waarmee een bestaand account kan worden overgenomen en een globaal rollenmodel waarmee tenantgebonden schrijfrechten kunnen worden omzeild. Daarnaast is de crawlerbescherming tegen SSRF niet bestand tegen DNS-rebinding, is de productie-API rechtstreeks op alle hostinterfaces gepubliceerd en ontbreken essentiële professionele waarborgen zoals MFA, sessie-intrekking, login-rate-limiting, security-auditlogging en een reproduceerbare softwareleveringsketen.

Er zijn ook aantoonbaar goede maatregelen: tenanttoegang wordt op veel objectroutes gecontroleerd, wachtwoorden worden met scrypt gehasht, OAuth-tokens worden versleuteld, OAuth-scopes zijn beperkt, database en Redis worden niet rechtstreeks op de host gepubliceerd, URL-validatie blokkeert private adressen en de renderercontainer heeft aanvullende sandboxmaatregelen. Deze maatregelen compenseren de kritieke tekortkomingen niet.

Professioneel gebruik kan opnieuw worden beoordeeld nadat minimaal de P0- en P1-maatregelen zijn geïmplementeerd en met regressietests en een onafhankelijke penetratietest zijn geverifieerd.

## Reikwijdte en beperkingen

Wel onderzocht:

- FastAPI-applicatie, autorisatie, gebruikers- en uitnodigingsflows;
- sessies, API-keygebruik, wachtwoordopslag en OAuth-implementatie;
- crawler- en rendererbeveiliging;
- Docker Compose, Dockerfiles en netwerkpublicatie;
- back-up- en restorescripts;
- dependencybeheer, tests en aanwezige operationele documentatie.

Niet aantoonbaar onderzocht:

- de werkelijk draaiende containers, reverse proxy, firewall en NAS-instellingen;
- productieomgeving, database-inhoud, actuele secrets en OAuth-providerconfiguratie;
- dynamische tests met meerdere echte gebruikers/tenants;
- internetbrede poortscan, externe TLS-scan of actieve aanvalstests;
- actuele CVE-scan van alle productiepackages en containerimages;
- cloud-, DNS-, e-mail- en overige leveranciersconfiguratie.

De browserlogin gaf geen veilige, volledige toegang tot bovenstaande serverconfiguratie. Afwezig bewijs is daarom als **niet aangetoond** beoordeeld, niet automatisch als kwetsbaar. Er zijn geen secrets of lokale back-ups geopend.

## Geprioriteerde bevindingen

### SEC-01 — Uitnodigingsflow maakt overname van bestaande accounts mogelijk

**Ernst:** Kritiek · **Prioriteit:** P0  
**ASVS:** authenticatie, account lifecycle, toegangsbeheer

**Bewijs:** `app/api/routes/users.py:216-257`. Wanneer het e-mailadres al bestaat, vervangt de publieke acceptatieroute zonder authenticatie de bestaande `password_hash`, activeert het account, voegt lidmaatschap toe en geeft direct een sessiecookie uit (`:225-252`).

**Impact:** een aanvaller die een uitnodiging voor het e-mailadres van een bestaand slachtoffer kan laten aanmaken, kan het wachtwoord vervangen en het account overnemen. Bij een beheerder of superuser kan dit toegang tot meerdere klanten opleveren. `_sync_global_role` vergroot bovendien de impact op het globale rollenmodel.

**Reproductie in een geïsoleerde testomgeving:**

1. Maak tenant A en een bestaand slachtofferaccount voor tenant B.
2. Laat een beheerder van tenant A het e-mailadres van het slachtoffer uitnodigen.
3. Open de uitnodigingslink zonder als slachtoffer ingelogd te zijn.
4. Accepteer met een nieuw wachtwoord.
5. Controleer dat het oude wachtwoord niet meer werkt en de response een sessie voor het slachtoffer bevat.

**Fix:** wijzig nooit het wachtwoord van een bestaand account via een tenantuitnodiging. Vereis dat de bestaande gebruiker eerst met zijn huidige authenticatiemiddel inlogt en daarna expliciet de uitnodiging accepteert. Gebruik voor nieuwe accounts een afzonderlijke, eenmalige activatieflow. Maak uitnodigingen doel-, tenant- en gebruikersgebonden, voorkom privilegeverhoging en trek alle nog openstaande tokens na acceptatie/intrekking in.

### SEC-02 — Globale rol omzeilt tenantgebonden read-onlyrechten

**Ernst:** Kritiek · **Prioriteit:** P0  
**ASVS:** object- en functieautorisatie, multi-tenancy

**Bewijs:** `app/services/authorization.py:12-52`. `require_write_access()` kijkt alleen naar `principal.role`; iedere rol anders dan `client` krijgt schrijfrecht. `require_client_access()` controleert wel lidmaatschap, maar combineert dit niet met de rol van dat specifieke lidmaatschap. Een gebruiker die ergens globaal `admin` wordt, kan daardoor bij een andere tenant met client/read-onlylidmaatschap mutaties uitvoeren.

**Impact:** ongeautoriseerde wijzigingen of verwijderingen in een andere klantomgeving; schending van tenantisolatie en mogelijk datalek of integriteitsverlies.

**Reproductie:**

1. Geef één gebruiker de rol `admin` in tenant A en `client` in tenant B.
2. Meld aan als die gebruiker.
3. Voer een muterende API-aanroep uit voor een object van tenant B die `require_write_access` en normale clienttoegang gebruikt.
4. Verwacht 403; de huidige logica kan de mutatie toestaan.

**Fix:** verwijder de globale afleiding van gewone tenantrollen. Autoriseer iedere actie op `(user, tenant, membership_role, resource, action)`. Reserveer een aparte platformrol voor echte platformbeheerders. Laat writechecks de concrete `ClientMembership` gebruiken. Voeg negatieve tests toe voor alle combinaties van admin/client over twee tenants en voor iedere muterende route.

### SEC-03 — SSRF-controle is kwetsbaar voor DNS-rebinding/TOCTOU

**Ernst:** Hoog · **Prioriteit:** P0  
**ASVS:** invoervalidatie, uitgaande verbindingen, SSRF

**Bewijs:** `app/services/security.py:8-24`. De validator resolveert de host en controleert `is_global`, waarna HTTPX of Chromium later opnieuw resolveert. De gecontroleerde en werkelijk gebruikte bestemming zijn niet cryptografisch of technisch aan elkaar gebonden.

**Impact:** een kwaadwillende website kan mogelijk de crawler laten verbinden met localhost, Docker-services, NAS, router, metadata-endpoints of andere interne systemen. De thuisworker vergroot dit bereik.

**Reproductie:** gebruik uitsluitend een testnetwerk en een gecontroleerd DNS-domein dat bij de eerste lookup een publiek IP en bij de volgende lookup een intern testadres retourneert. Start een crawl en controleer op de interne testservice of de tweede verbinding aankomt. Test hetzelfde na redirects en voor IPv6.

**Fix:** isoleer crawling in een netwerk zonder route naar beheer-, privé-, metadata- of productienetwerken en hanteer egress-allow/denyregels. Resolveer en valideer elk doel vlak voor verbinding, pin de verbinding aan het goedgekeurde IP, behoud de juiste TLS-hostnaam/SNI en herhaal dit na iedere redirect. Blokkeer alle niet-benodigde protocollen, poorten en IP-ranges. Gebruik korte time-outs, downloadlimieten en DNS-beveiliging. Beschouw applicatievalidatie als tweede laag, niet als netwerkgrens.

### SEC-04 — Productie-API is rechtstreeks op alle hostinterfaces gepubliceerd

**Ernst:** Hoog · **Prioriteit:** P0  
**ASVS:** communicatiebeveiliging, deployment

**Bewijs:** `compose.prod.yaml:1-4` publiceert `${API_PORT:-8000}:8000`; zonder hostadres betekent dit alle interfaces. De basisconfiguratie doet hetzelfde in `compose.yaml:2-6`.

**Impact:** een aanvaller kan mogelijk reverse-proxymaatregelen, TLS, headers, toegangscontrole of rate limits omzeilen door poort 8000 rechtstreeks te benaderen.

**Reproductie:** controleer vanaf een tweede systeem in hetzelfde en, indien toegestaan, externe netwerk of `http://host:8000` bereikbaar is en vergelijk headers/gedrag met de HTTPS-hostnaam.

**Fix:** bind uitsluitend aan `127.0.0.1:8000:8000` of gebruik een intern Compose-netwerk zonder hostpublicatie. Sta extern alleen 443 via de reverse proxy toe en verifieer dit met hostfirewall en een scan vanaf buiten de host.

### SEC-05 — Geen aantoonbare login-rate-limiting of MFA

**Ernst:** Hoog · **Prioriteit:** P0 voor beheerders, P1 algemeen  
**ASVS:** authenticatie, anti-automatisering

**Bewijs:** in de beschikbare login- en gebruikersflow is geen per-account/per-IP rate-limit, lockout/backoff of tweede factor aangetroffen. Wachtwoorden zijn wel minimaal twaalf tekens en met scrypt gehasht (`app/core/security.py:50-73`).

**Impact:** credential stuffing en brute force; één gestolen beheerderswachtwoord kan alle tenants raken.

**Reproductie:** voer in staging een begrensde reeks foutieve logins uit en controleer dat alle verzoeken zonder oplopende vertraging/429 worden verwerkt. Controleer dat een beheerder met alleen een wachtwoord kan aanmelden.

**Fix:** verplicht phishing-resistente MFA of minimaal TOTP voor platform- en tenantbeheerders; bied MFA aan alle gebruikers. Voeg samengestelde rate limits, progressieve vertraging, detectie en notificatie toe zonder accountenumeratie. Leg recoverycodes en herstelproces veilig vast.

### SEC-06 — Sessies zijn twaalf uur geldig en niet centraal intrekbaar

**Ernst:** Hoog · **Prioriteit:** P1  
**ASVS:** sessiebeheer

**Bewijs:** `app/core/security.py:17-43` maakt stateless HMAC-tokens met een vaste TTL van twaalf uur. Er is geen sessie-ID, server-side sessiestatus, rotatie of revocatielijst. Dezelfde algemene `API_KEY` tekent de sessies (`:23-25`, `:40-42`).

**Impact:** gestolen sessies blijven bruikbaar tot verlopen; uitloggen, wachtwoordwijziging of rolverlaging kan een reeds uitgegeven token niet betrouwbaar intrekken. Compromittering of rotatie van de API-key raakt zowel API-authenticatie als alle sessies.

**Reproductie:** kopieer in staging een geldige sessiecookie, log uit of wijzig het wachtwoord en hergebruik de oude cookie. Verwacht 401; de tokenstructuur biedt daar nu geen mechanisme voor.

**Fix:** gebruik een afzonderlijke sessiesigningkey en bij voorkeur server-side sessieregistratie met opaque, geroteerde tokens. Trek sessies in bij logout, wachtwoordwijziging, accountdeactivatie en privilegewijziging. Toon actieve sessies en ondersteun ‘log overal uit’. Verkort en differentieer adminsessies.

### SEC-07 — Eén API-key geeft volledige superuserrechten

**Ernst:** Hoog · **Prioriteit:** P1  
**ASVS:** authenticatie, least privilege, secrets

**Bewijs:** `app/core/security.py:83-95`; iedere geldige `X-API-Key` wordt `Principal(... role="superuser", is_api_key=True)`. Autorisatiehelpers laten `is_api_key` vervolgens overal door (`app/services/authorization.py:12-50`).

**Impact:** verlies van één gedeeld geheim geeft platformbrede toegang en biedt weinig bron-, scope- of tenantattributie.

**Reproductie:** gebruik in staging de algemene key op routes van verschillende tenants en controleer dat dezelfde key alle objecten en functies bereikt.

**Fix:** vervang de algemene key door afzonderlijke service-identiteiten met tenant-, functie- en omgevingsscopes, korte geldigheid, rotatie en auditlogging. Gebruik mTLS of ondertekende workloadtokens waar passend. Scheid menselijke, worker- en beheertoegang.

### SEC-08 — Tenantbeheerder kan bestaande leden tot admin promoveren

**Ernst:** Hoog · **Prioriteit:** P1  
**ASVS:** functieautorisatie, privilegebeheer

**Bewijs:** de ledenwijzigingsflow in `app/api/routes/users.py` laat een tenantadmin de rol van een bestaand lid aanpassen; de beperkingen van de uitnodigingsroute worden niet consequent op rolwijzigingen toegepast.

**Impact:** onverwachte privilege-escalatie binnen een tenant en inconsistent beleid rond wie beheerders mag creëren.

**Reproductie:** laat een tenantadmin via de PATCH-route een clientlid naar admin wijzigen en vergelijk dit met de beperktere uitnodigingsroute.

**Fix:** leg één expliciete rolmatrix vast en gebruik dezelfde beleidsfunctie voor uitnodigen, toevoegen en wijzigen. Vereis herauthenticatie/MFA voor adminpromotie, voorkom dat de laatste admin zichzelf uitschakelt en audit/notificeer iedere wijziging.

### SEC-09 — OAuth-state is niet gebonden aan sessie en niet eenmalig

**Ernst:** Middel · **Prioriteit:** P1  
**ASVS:** OAuth/OIDC, sessiekoppeling

**Bewijs:** `app/services/oauth.py` ondertekent state met een geldigheidsduur, maar de state bevat alleen de clientcontext en geen server-side nonce die aan de initiërende gebruikerssessie is gekoppeld en na gebruik wordt verbruikt.

**Impact:** OAuth login-/connect-CSRF, hergebruik van callback-state binnen het geldigheidsvenster en verwarring over welk account de koppeling startte.

**Reproductie:** start een koppeling, bewaar de callback/state en probeer dezelfde state binnen de geldigheidsduur opnieuw of vanuit een andere ingelogde browsersessie te gebruiken.

**Fix:** genereer een cryptografisch willekeurige, eenmalige nonce; sla alleen een hash server-side op met user-, sessie-, tenant-, provider- en redirectbinding; consumeer atomair bij callback. Gebruik PKCE waar van toepassing en exacte redirect-URI’s.

### SEC-10 — CSRF-bescherming steunt hoofdzakelijk op cookiegedrag

**Ernst:** Middel · **Prioriteit:** P1  
**ASVS:** sessies, requestintegriteit

**Bewijs:** sessiecookies zijn `HttpOnly`, productie-`Secure` en `SameSite=Lax` (`app/api/routes/users.py:250-257`), maar er is geen algemene synchronizer/double-submit-token of strikte Origin-verificatie aangetroffen voor alle mutaties.

**Impact:** toekomstige routes, contenttypes of browsergedrag kunnen statuswijzigende requests mogelijk maken vanuit een andere origin. XSS vergroot het risico.

**Reproductie:** inventariseer in staging alle muterende endpoints en probeer cross-origin formulier-, fetch- en contenttypevarianten; controleer Origin/Referer-afwijzing en preflightgedrag.

**Fix:** voeg centrale CSRF-bescherming toe voor cookiegeauthenticeerde mutaties, valideer Origin/Host, accepteer alleen verwachte contenttypes en behoud passende SameSite-cookies. Test alle muterende routes.

### SEC-11 — Secrets worden breed gedeeld en lokaal onvoldoende beschermd

**Ernst:** Hoog · **Prioriteit:** P1  
**ASVS:** secretsmanagement, least privilege

**Bewijs:** vrijwel iedere service ontvangt dezelfde volledige `.env` (`compose.yaml:2-143`). Het lokale `.env`-bestand had tijdens de audit modus `0644`. Standaard databasecredentials vallen terug op `seo/seo` (`compose.yaml:144-150`).

**Impact:** compromittering van één worker kan onnodig database-, OAuth-, encryptie-, API- en bootstrapgeheimen blootleggen. Wereldleesbare lokale rechten vergroten het risico op uitlekken via andere lokale processen/accounts.

**Reproductie:** vergelijk per container de beschikbare omgevingsvariabelen met de werkelijk benodigde rechten; controleer bestandsrechten zonder waarden te tonen.

**Fix:** verstrek per service alleen noodzakelijke secrets, gebruik afzonderlijke serviceaccounts en databasecredentials, zet secretbestanden op `0600`, verbied onveilige defaults in productie en implementeer rotatie/intrekking. Gebruik Docker secrets of een passend EU-gehost secretsysteem; log nooit waarden.

### SEC-12 — Containers draaien grotendeels als root en missen uniforme hardening

**Ernst:** Hoog · **Prioriteit:** P1  
**ASVS:** deployment, sandboxing

**Bewijs:** `Dockerfile:1-8` definieert geen niet-rootgebruiker. Alleen de renderer krijgt aantoonbaar `no-new-privileges`, capability-drop en resourcegrenzen (`compose.yaml:103-130`).

**Impact:** een applicatie- of dependency-exploit heeft meer privileges in de container en kan makkelijker bestanden, volumes en aangrenzende diensten misbruiken.

**Reproductie:** controleer `id`, capabilities, writeable filesystems en resourcegrenzen in iedere draaiende container.

**Fix:** draai alle applicatiecontainers met een vaste niet-root UID/GID; maak rootfilesystem read-only waar mogelijk; drop capabilities; zet `no-new-privileges`; beperk PID, CPU en geheugen; gebruik tijdelijke tmpfs-mounts en minimale volumes. Houd Chromium extra geïsoleerd.

### SEC-13 — Back-upset is onvolledig en niet ransomwarebestendig aangetoond

**Ernst:** Hoog · **Prioriteit:** P1  
**ASVS:** databescherming, beschikbaarheid

**Bewijs:** `scripts/backup.sh` maakt een PostgreSQL-dump, controleert leesbaarheid en checksum en verwijdert na standaard dertig dagen. De repository bevat geen werkende versleutelde onafhankelijke off-sitekopie. Exports, configuratie en de sleutel die nodig is om OAuth-data te herstellen zijn niet onderdeel van dit script. `scripts/restore.sh` controleert de checksum alleen wanneer het checksumbestand bestaat.

**Impact:** na verlies of compromittering van NAS/productie kunnen back-ups ontbreken of worden verwijderd. Een database kan herstelbaar zijn terwijl bestanden of decryptiesleutels ontbreken; een restore zonder checksum kan ongemerkt een verkeerd/beschadigd bestand accepteren.

**Reproductie:** voer in een geïsoleerde herstelomgeving een volledige restore uit vanaf alleen de gedocumenteerde back-upset en controleer database, exports, OAuth-koppelingen, configuratie en benodigde secrets. Test dat restore zonder checksum hard faalt.

**Fix:** maak minimaal één versleutelde, immutable of administratief geïsoleerde EU-back-up; neem database, duurzame bestanden, noodzakelijke configuratie en apart beheerde herstelgeheimen op. Maak checksum verplicht, gebruik langere gelaagde retentie, test periodiek bare-metal/applicatie/databaseherstel en meet RPO/RTO. Geef productie geen verwijderrecht op ten minste één kopie.

### SEC-14 — Security-auditlogging en detectie zijn onvoldoende

**Ernst:** Hoog · **Prioriteit:** P1  
**ASVS:** logging, monitoring, incidentrespons

**Bewijs:** er is gestructureerde operationele logging, maar geen aantoonbaar compleet, beschermd security-auditregister voor loginpogingen, uitnodigingen, rolwijzigingen, OAuth-koppelingen, API-keygebruik, exports en beheerdersacties.

**Impact:** accountmisbruik en cross-tenantactiviteiten worden mogelijk laat ontdekt; reconstructie, klantmelding en forensisch onderzoek zijn beperkt.

**Reproductie:** voer de genoemde acties in staging uit en controleer of actor, tenant, actie, doel, tijd, bron en resultaat zonder secrets in een wijzigingsbestendig register verschijnen en relevante alerts afgaan.

**Fix:** ontwerp een afzonderlijk audit-eventmodel; bescherm tegen wijziging/verwijdering door gewone applicatiebeheerders; centraliseer binnen de EU; definieer retentie en alerts. Log geen tokens of payloads met klantdata. Test detectieregels en incidentprocedure.

### SEC-15 — Dependency- en buildketen is niet reproduceerbaar of automatisch bewaakt

**Ernst:** Hoog · **Prioriteit:** P1  
**ASVS:** veilige ontwikkeling, dependencybeheer

**Bewijs:** `pyproject.toml` gebruikt brede versieruimtes; er is geen lockfile met hashes gevonden en geen repositoryconfiguratie voor CI, dependency-, secret-, SAST- of container-image-scanning. `Dockerfile:4-5` installeert direct vanuit `pyproject.toml`. De lokale venv gebruikt Python 3.13 terwijl het image Python 3.12 gebruikt.

**Impact:** builds kunnen zonder codewijziging veranderen; kwetsbare of kwaadwillende dependencies kunnen productie bereiken; lokale tests zijn minder representatief.

**Reproductie:** bouw dezelfde commit op twee momenten zonder cache en vergelijk package-inventaris/SBOM en image-digest.

**Fix:** pin Python en dependencies; commit een lockfile met hashes; bouw één gecontroleerd image dat tussen omgevingen wordt gepromoveerd; genereer een SBOM; scan dependencies, secrets, code en images; blokkeer kritieke/hoge bevindingen volgens vastgestelde uitzonderingsprocedure; bescherm de hoofdbranch en verplicht review.

### SEC-16 — Geautomatiseerde securitytests konden niet betrouwbaar worden uitgevoerd

**Ernst:** Middel · **Prioriteit:** P1  
**ASVS:** verificatie en secure development lifecycle

**Bewijs:** linting slaagde en `pip check` vond geen dependencyconflicten. Zowel een geselecteerde brede testset als `tests/test_security.py` bleef tijdens pytestinitialisatie/import hangen in de lokale gesynchroniseerde omgeving. Er is dus geen geslaagd testrapport. `pip check` is geen CVE-scan.

**Impact:** bestaande positieve en negatieve tests leveren op dit moment geen releasebewijs; regressies kunnen ongemerkt blijven.

**Fix:** voer tests in een lokale niet-gesynchroniseerde werkmap of CI uit met Python 3.12, een geïsoleerde testdatabase en vaste dependencies. Publiceer testresultaten. Voeg expliciete regressietests toe voor SEC-01, SEC-02 en SEC-03 en dynamische autorisatiematrixtests voor alle muterende routes.

## Positieve controles

- Veel resource- en websiteroutes gebruiken centrale tenanttoegangscontroles.
- Negatieve tenanttests zijn in de repository aanwezig, al konden ze in deze audit niet worden uitgevoerd.
- Wachtwoorden gebruiken scrypt met willekeurig salt en constante-tijdvergelijking.
- Sessiecookies zijn `HttpOnly`, in productie `Secure` en `SameSite=Lax`.
- OAuth-tokens worden met Fernet versleuteld en de OAuth-scopes zijn beperkt/read-only ontworpen.
- URL-validatie accepteert alleen HTTP(S), resolveert DNS en weigert niet-globale adressen.
- Redirects en responseomvang worden begrensd in de crawlerimplementatie.
- PostgreSQL en Redis zijn in de aangetroffen Compose-configuratie niet rechtstreeks op hostpoorten gepubliceerd.
- De renderer heeft PID-/geheugen-/CPU-limieten, capability-drop en `no-new-privileges`.
- Back-updump wordt atomair opgebouwd, op inhoud controleerbaar gemaakt en van een SHA-256-bestand voorzien.
- Restore weigert volgens de scripts actieve schrijvers en operationele logs zijn gestructureerd in UTC.

## Aansluiting op OWASP ASVS niveau 2

| ASVS-gebied | Oordeel | Kernreden |
|---|---|---|
| Architectuur en threat modelling | Gedeeltelijk | Goede documentatie, maar geen volledig aantoonbaar threat model/controlregister |
| Authenticatie | Onvoldoende | Account takeover, geen MFA/rate-limit |
| Sessiebeheer | Onvoldoende | Niet-intrekbare stateless sessies, gedeelde sleutel |
| Toegangsbeheer | Onvoldoende | Kritieke cross-tenant write-bypass |
| Validatie en business logic | Onvoldoende | SSRF TOCTOU en invitation-businesslogica |
| Cryptografie | Gedeeltelijk | Scrypt/Fernet positief; key lifecycle en scheiding onvoldoende bewezen |
| Foutafhandeling en logging | Onvoldoende | Geen compleet security-auditregister/detectie |
| Databescherming | Onvoldoende | Back-upset en immutable off-siteherstel niet aangetoond |
| Communicatie | Niet aangetoond | Werkelijke TLS/proxy/firewallconfiguratie niet beschikbaar; directe API-publicatie risicovol |
| Schadelijke code/dependencies | Onvoldoende | Geen lockfile of geautomatiseerde supply-chainscans |
| API en webservices | Onvoldoende | Globale API-key en autorisatieproblemen |
| Configuratie en deployment | Onvoldoende | Rootcontainers, breed gedeelde secrets, directe hostpoort |

**Conclusie:** aansluiting op ASVS niveau 2 is niet behaald en ook nog niet volledig verifieerbaar. Een formele claim vereist een controle per toepasselijke ASVS-eis met bewijs, testresultaat, eigenaar en uitzonderingsregistratie.

## Herstelplan en vrijgavepoort

### P0 — vóór nieuwe professionele klanten of gevoelige integraties

1. Stop het resetten van bestaande wachtwoorden via uitnodigingen; beoordeel en trek risicovolle openstaande uitnodigingen in.
2. Vervang globale writechecks door tenantgebonden autorisatie en test iedere muterende route cross-tenant.
3. Isoleer crawler/renderers op netwerkniveau en verhelp DNS-rebinding/redirect-SSRF.
4. Sluit poort 8000 extern; alleen reverse proxy/TLS mag bereikbaar zijn.
5. Verplicht MFA voor platform- en tenantbeheerders en voeg login-rate-limiting toe.

### P1 — vóór formele kwalificatie als professioneel platform

1. Introduceer intrekbare sessies en scoped workloadidentiteiten.
2. Herontwerp secrets per service en harden alle containers.
3. Implementeer security-auditlogging, alerts en incidentrespons.
4. Maak versleutelde, verwijderbeschermde EU-off-siteback-ups en voer een volledige restoretest uit.
5. Maak builds reproduceerbaar; voeg CI, lockfile, SBOM en scans toe.
6. Bind OAuth-state aan sessie/user/tenant en maak hem eenmalig.
7. Implementeer uniforme CSRF- en rolwijzigingscontroles.

### Verplichte verificatie vóór GO

- alle P0/P1-regressietests slagen in CI op Python 3.12;
- volledige tenantautorisatiematrix is groen voor API, exports, jobs, caches en workers;
- gerichte SSRF-test omvat IPv4, IPv6, redirects, DNS-rebinding en interne Docker-/NAS-doelen;
- externe scan toont alleen bedoelde publieke poorten en correcte TLS/securityheaders;
- actuele dependency-, secret-, SAST- en imagescans hebben geen onbehandelde kritieke/hoge bevindingen;
- volledige restore uit onafhankelijke back-up haalt de vastgestelde RPO/RTO;
- onafhankelijke penetratietest vindt geen kritieke/hoge open bevindingen;
- ASVS-L2-controlmatrix is ingevuld met bewijs en formeel geaccepteerde uitzonderingen.

## Eindbesluit

**Huidig: NO-GO voor professioneel multi-tenant gebruik met externe klantdata.**

Beperkt intern testen kan uitsluitend met niet-gevoelige testdata, expliciete risicoacceptatie, afgeschermde netwerktoegang en zonder waardevolle OAuth-koppelingen. De account-overname, tenantautorisatie en SSRF/netwerkisolatie zijn releaseblokkerend. Na herstel van P0 en P1 is een nieuwe code-audit plus onafhankelijke penetratietest nodig voordat het oordeel naar GO kan veranderen.

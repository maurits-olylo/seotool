# Back-up- en herstelbeleid

Status: Release 7a-B fase 6A lokaal, op staging en op productie geaccepteerd, inclusief dagelijkse
planning en waarschuwing bij mislukking.

## Reikwijdte fase 6A

Iedere back-up is één versleuteld herstelpakket met:

- een leesbaar gevalideerde PostgreSQL custom-format dump;
- het volledige duurzame exportvolume;
- het environmentbestand dat database-, OAuth- en tokenencryptieherstel mogelijk maakt;
- de exacte Git-commit, omgeving en databasedoel in een niet-geheim manifest;
- afzonderlijke SHA-256-controles voor ieder onderdeel en voor het versleutelde eindbestand.

Redis, containerimages, caches, tijdelijke bestanden en logs zonder afzonderlijke bewaarplicht zijn
bewust uitgesloten. Redis bevat vervangbare queue- en cachetoestand. Code en images worden vanaf de
vastgelegde Git-commit opnieuw opgebouwd.

De pakketversleuteling gebruikt OpenSSL AES-256-CBC met PBKDF2-HMAC-SHA-256 en 600.000 iteraties.
Transport naar een volgende locatie mag uitsluitend via TLS of de bestaande SSH-route verlopen;
het pakket blijft daarbij al cliënt-side versleuteld.

## Sleutelbeheer

Maak de sleutel uitsluitend met `scripts/configure-backup-key.sh`. Het script toont de waarde
niet, weigert een bestaande sleutel te overschrijven en valideert modus `0600`. Bewaar de primaire
herstelsleutel niet in Git, het project, het back-upvolume of logs. Bewaar minimaal één afzonderlijk
beveiligd herstelkopie. Sleutelrotatie vereist een apart venster waarin oude pakketten met hun oude
sleutel herstelbaar blijven totdat zij volgens beleid verlopen.

Een verloren sleutel maakt alle bijbehorende pakketten onherstelbaar. Een sleutel naast het pakket
neemt de belangrijkste bescherming bij diefstal of verlies weg.

## Herstelnormen

- Voorlopig RPO: maximaal 24 uur bij één geslaagde dagelijkse back-up.
- Voorlopig RTO: maximaal 4 uur voor database, exports, configuratie, migraties en healthcontrole.
- Een back-up is pas geslaagd nadat database, exportarchief, encryptie, eindarchief en checksums
  zijn gevalideerd.
- `scripts/check-backup.sh` faalt standaard wanneer het nieuwste pakket ouder is dan 30 uur, niet
  decryptable is, een verkeerde checksum heeft of geen leesbaar archief bevat.
- Iedere geslaagde uitvoering vernieuwt een omgevingsgebonden `latest`-verwijzing pas nadat pakket
  en checksum volledig zijn gepubliceerd; herstelcommando's hoeven daardoor geen glob te gebruiken.
- `scripts/scheduled-backup.sh` voorkomt overlap, activeert de crawl-drain, stopt tijdelijk de drie
  overige achtergrondschrijvers, maakt en controleert de back-up en herstelt services en drain ook
  wanneer een tussenstap faalt. De oorspronkelijke foutstatus blijft behouden voor DSM-melding.
- De definitieve RPO en RTO worden vervangen door de werkelijk gemeten waarden uit de geïsoleerde
  stagingrestore.

De stagingrestore van 6 augustus 2026 bevestigde volledige leesbaarheid en privacyherhaling. De
beschikbare terminalregistratie bevat geen betrouwbare gezamenlijke start- en eindtijd; het RTO van
vier uur blijft daarom voorlopig en wordt bij de eerste geplande volledige herstelmeting met
expliciete tijdmarkers vervangen door een gemeten waarde.

De eerste productie-uitvoering op 6 augustus 2026 publiceerde en controleerde een volledig
versleuteld pakket terwijl crawls veilig waren gedraind en overige achtergrondschrijvers tijdelijk
waren gestopt. Alle services waren daarna gezond en de drain werd zonder hervatte taken opgeheven.
Productie is niet als hersteltest gebruikt; de volledige restoreproef blijft uitsluitend op de
synthetische stagingomgeving uitgevoerd.

De dagelijkse DSM-roottaak `SEO Monitor encrypted backup` is om 03:00 ingeschakeld met e-mail bij
abnormale beëindiging. De handmatige acceptatierun van 6 augustus 2026 liep van 23:07:22 tot
23:15:03 en eindigde met DSM-status `Normal (0)`. Daarmee zijn ook de foutdoorgifte voor monitoring
en de volledige geplande wrapperroute operationeel geaccepteerd. De oude database-only taak blijft
uitgeschakeld en mag worden verwijderd; twee gelijktijdige back-uptaken zijn niet toegestaan.

## Privacy na herstel

Een afzonderlijk Docker-volume bewaart verwijderingen van klanten en websites buiten het
databasevolume als minimale JSONL-regels met alleen objecttype, UUID en UTC-verwijdertijd. Het
register bevat geen namen, e-mailadressen of andere klantinhoud. Iedere back-up neemt een
bewijsafschrift op, maar overschrijft bij een normale restore nooit automatisch het actuelere
register. `restore.sh` past het actuele register na databaseherstel automatisch en idempotent toe.

Een restore mag schrijvende services niet automatisch starten. Na database- en exportherstel
blijven zij gestopt totdat de uitvoer van `reapply-privacy-deletions` is gecontroleerd. Alleen bij
verlies van het volledige privacyvolume mag een bevoegde beheerder bewust
`RESTORE_PRIVACY_LEDGER_IF_EMPTY=true` gebruiken om het afschrift uit het herstelpakket te plaatsen.
Fase 6B maakt ook het nieuwste onafhankelijke register buiten de NAS herstelbaar.

Productiedata wordt niet naar development gekopieerd. Hersteltests gebruiken synthetische
stagingdata in een afzonderlijk Compose-project en afzonderlijke volumes. Alleen een later expliciet
goedgekeurd, afgeschermd productieherstel mag een echt productiepakket ontsleutelen.

## Onafhankelijke EU-kopie

De gekozen tweede locatie is Scaleway Object Storage in Parijs, klasse `Standard Multi-AZ`.
De koppeling gebruikt uitsluitend de algemene S3-API; een andere compatibele EU-provider blijft
daardoor technisch mogelijk. Het pakket is al lokaal versleuteld voordat het de NAS verlaat.

`scripts/offsite-backup.py` uploadt de unieke timestampversie, bewaart de lokale SHA-256 als
objectmetadata en controleert daarna omvang, checksummetadata en Object Lock-retentie. Alleen
`COMPLIANCE` wordt geaccepteerd. Een gewone beheerder of gecompromitteerde NAS-uploadcredential kan
het object gedurende de retentie daardoor niet verwijderen of overschrijven.

Geheimen staan in twee root-only bestanden buiten het project:

- `offsite-backup.env` met endpoint, regio, bucket, prefix, retentie en het credentialpad;
- het credentialbestand met uitsluitend `AWS_ACCESS_KEY_ID` en `AWS_SECRET_ACCESS_KEY`.

Beide bestanden moeten modus `0600` of `0400` hebben. De NAS-credential krijgt alleen upload,
objectmetadata- en retentieleesrechten op de productieprefix; geen delete-, lifecycle-,
bucketbeheer- of retention-bypassrecht. Een afzonderlijke herstelcredential blijft buiten de NAS.
De bucket gebruikt versioning en een standaardretentie van dertig dagen in `COMPLIANCE`-modus.
Plaats de uploadcredential uitsluitend met `scripts/configure-offsite-backup.sh`. Het script leest
beide waarden verborgen in, weigert bestaande configuratie te overschrijven en toont geen secrets.

De dagelijkse wrapper uploadt pas na lokale checksum-, decryptie- en archiefcontrole. Een mislukte
upload of ontbrekende COMPLIANCE-retentie maakt de hele geplande taak rood, terwijl services en
crawl-drain via de bestaande cleanup altijd worden hersteld.

Een herstelproef begint op een afzonderlijk systeem met de herstelcredential:

```bash
python3 scripts/offsite-backup.py download \
  seo-monitor/production/seo-monitor-production-YYYYMMDDTHHMMSSZ.tar.enc \
  /veilige/herstelmap/seo-monitor-production-YYYYMMDDTHHMMSSZ.tar.enc
```

Daarna controleert `scripts/check-backup.sh` het gedownloade pakket en voert `scripts/restore.sh`
de bestaande geïsoleerde restoreprocedure uit. Een proef telt pas wanneer NAS-back-upvolume en
NAS-uploadcredential daarbij niet zijn gebruikt.

## Retentie

Fase 6A behoudt lokaal standaard 30 dagen en verwijdert alleen correct benoemde versleutelde
pakketten en hun checksum na afloop. Verlenging naar gelaagde dagelijkse, wekelijkse en maandelijkse
retentie volgt op basis van gemeten pakketgroei.

De implementatie voor fase 6B is gereed voor providerconfiguratie en acceptatie. De gate sluit pas
na een echte upload, aantoonbaar geweigerde verwijdering en een restore uit uitsluitend Scaleway:

De eerste echte upload is op 12 augustus 2026 geslaagd. Het script controleerde het remote object
op omvang, SHA-256-metadata en `COMPLIANCE`-retentie. Het concrete objectpad en provideridentifiers
worden bewust niet in Git-documentatie vastgelegd.

- stel lifecycle pas in nadat is bewezen dat deze geen beschermde versies vóór beleidseinde raakt;
- meet opslaggroei en stel een kostenwaarschuwing bij de provider in;
- bewaar de herstelsleutel en herstelcredential aantoonbaar buiten de NAS.

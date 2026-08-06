# Back-up- en herstelbeleid

Status: Release 7a-B fase 6A lokaal en op staging gevalideerd; productieacceptatie volgt.

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
- De definitieve RPO en RTO worden vervangen door de werkelijk gemeten waarden uit de geïsoleerde
  stagingrestore.

De stagingrestore van 6 augustus 2026 bevestigde volledige leesbaarheid en privacyherhaling. De
beschikbare terminalregistratie bevat geen betrouwbare gezamenlijke start- en eindtijd; het RTO van
vier uur blijft daarom voorlopig en wordt bij de eerste geplande volledige herstelmeting met
expliciete tijdmarkers vervangen door een gemeten waarde.

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

## Retentie en fase 6B

Fase 6A behoudt lokaal standaard 30 dagen en verwijdert alleen correct benoemde versleutelde
pakketten en hun checksum na afloop. Verlenging naar gelaagde dagelijkse, wekelijkse en maandelijkse
retentie volgt op basis van gemeten pakketgroei.

Release 7a-B fase 6B blijft een harde gate vóór Friends & Family en voegt toe:

- een tweede onafhankelijke opslaglocatie in de EU;
- Object Lock of gelijkwaardige immutability zonder verwijderrecht voor productie;
- automatische lifecycle en kostenbegrenzing;
- herstel vanaf uitsluitend de onafhankelijke kopie;
- operationeel bewijs dat verlies van NAS, project en productiecredentials kan worden overleefd.

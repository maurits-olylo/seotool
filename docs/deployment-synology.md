# Deployment op Synology NAS

## Vereisten

- Synology Container Manager met Docker Compose-ondersteuning.
- SSH-toegang voor installatie en beheer.
- Een NAS-map, bijvoorbeeld `/volume1/docker/seo-monitor`.
- Een reverse proxy met HTTPS wanneer de API buiten het lokale netwerk beschikbaar is.
- Voldoende opslag voor PostgreSQL, snapshots, exports en back-ups.

## Mapstructuur

```text
/volume1/docker/seo-monitor/
├── project/      # repository en .env
└── backups/      # pg_dump-bestanden, buiten Git
```

## Environment

```bash
cd /volume1/docker/seo-monitor/project
cp .env.example .env
chmod 600 .env
```

Gebruik in productie minimaal:

```dotenv
APP_ENV=production
API_KEY=een-lange-willekeurige-geheime-waarde
INITIAL_SUPERUSER_EMAIL=maurits@thact.nl
INITIAL_SUPERUSER_PASSWORD=een-uniek-wachtwoord-van-minimaal-12-tekens
POSTGRES_DB=seo
POSTGRES_USER=seo
POSTGRES_PASSWORD=een-ander-lang-wachtwoord
DATABASE_URL=postgresql+psycopg://seo:URL_ENCODED_WACHTWOORD@postgres:5432/seo
API_PORT=8000
```

Gebruik geen spaties of on-geëscapete speciale tekens in `DATABASE_URL`. Commit `.env` nooit.

## Installeren en starten

```bash
docker compose -f compose.yaml -f compose.prod.yaml build
docker compose -f compose.yaml -f compose.prod.yaml up -d postgres redis
docker compose -f compose.yaml -f compose.prod.yaml run --rm api alembic upgrade head
docker compose -f compose.yaml -f compose.prod.yaml up -d
docker compose -f compose.yaml -f compose.prod.yaml ps
curl http://127.0.0.1:8000/health
```

Stel in Synology Reverse Proxy HTTPS in en stuur verkeer door naar poort `API_PORT`. Beperk toegang
waar mogelijk via firewall of VPN. De API-key blijft ook achter de reverse proxy verplicht voor
technische API-clients. Teamleden loggen in met hun persoonlijke account; het initiële beheeraccount
komt uit de environment.

## Afzonderlijke staging op dezelfde NAS

Staging gebruikt uitsluitend `compose.staging.yaml`, `.env.staging` en de vaste Compose-projectnaam
`seo-monitor-staging`. De stack bevat alleen API, PostgreSQL en Redis. Er zijn bewust geen workers
of scheduler opgenomen.

Maak na het uitpakken van een release in de interactieve NAS-shell een eigen configuratie. Gebruik
andere geheimen dan productie en plaats uitsluitend synthetische testdata in deze database:

```bash
cd /volume1/docker/seo-monitor/project
sudo cp .env.staging.example .env.staging
sudo chmod 600 .env.staging
sudo vi .env.staging
```

Controleer vóór de eerste start dat staging zelfstandig is en uitsluitend op loopback publiceert:

```bash
sudo docker compose --env-file .env.staging -f compose.staging.yaml config --services
sudo docker compose --env-file .env.staging -f compose.staging.yaml config \
  | grep -E '127\.0\.0\.1|seo-monitor-staging-(postgres|redis|exports)-data'
```

De eerste opdracht moet exact `api`, `postgres` en `redis` tonen. Start daarna eerst de
gegevensdiensten, voer de migraties uit en start de API:

```bash
sudo docker compose --env-file .env.staging -f compose.staging.yaml build api
sudo docker compose --env-file .env.staging -f compose.staging.yaml up -d postgres redis
sudo docker compose --env-file .env.staging -f compose.staging.yaml run --rm api alembic upgrade head
sudo docker compose --env-file .env.staging -f compose.staging.yaml up -d api
sudo docker compose --env-file .env.staging -f compose.staging.yaml ps
curl --fail --silent --show-error http://127.0.0.1:18000/health
```

Open vanaf de Mac een tijdelijke tunnel in het lokale terminalvenster. Houd dit venster open en
bezoek vervolgens `http://127.0.0.1:18000/ui/assets/index.html`:

```bash
ssh -N -L 18000:127.0.0.1:18000 thact@192.168.2.20
```

Stoppen bewaart de stagingdata. `down --volumes` is niet toegestaan in de normale werkwijze:

```bash
sudo docker compose --env-file .env.staging -f compose.staging.yaml stop
```

Gebruik voor een expliciete stagingproef van back-up of restore altijd `COMPOSE_TARGET=staging` en
de stagingdatabasenaam en -gebruiker. Zonder deze variabele richten de scripts zich bewust op
productie.

De Synology-kernel ondersteunt geen Docker `NanoCPUs` en in deze installatie ook geen PIDs-limiet.
Daarom gebruikt staging relatieve CPU-prioriteiten (`cpu_shares`) en uitsluitend harde
geheugenlimieten; dit is geen absolute CPU-cap. Voer builds met `sudo nice -n 10` uit. Controleer
tijdens de eerste build en proef met `docker stats` en `docker system df` de belasting. Productie
krijgt altijd voorrang; stop staging wanneer productie merkbaar wordt beïnvloed.

## Updates

### Terminal-first en DSM-interface

Beheer productie en staging standaard vanuit de bestaande interactieve NAS-shell. Gebruik de
Container Manager-interface alleen wanneer een handeling niet veilig via de terminal kan worden
uitgevoerd. Controleer een noodzakelijk klikpad vooraf tegen de officiële documentatie voor de
actuele DSM-hoofdversie en geef altijd:

- de exacte Nederlandse namen van toepassing, sectie, knop en scherm;
- de verwachte zichtbare inhoud vóór een wijziging;
- een expliciet stopmoment wanneer de interface afwijkt;
- een waarschuwing vóór acties die containers, images, netwerken of volumes kunnen verwijderen.

Gebruik `Opschonen` en `Verwijderen` nooit voor inspectie. Synology beschrijft `Opschonen` als
`docker-compose down`, waarbij containers, netwerken, volumes en projectimages kunnen worden
verwijderd.

### Vaste route: releasepakket via Mac

Maak iedere release op de Mac vanaf een exacte commit met `git archive`. Upload nooit met SCP en
gebruik geen Git op de NAS. Stream het archief naar `/tmp`, controleer daar de checksum en pak het
met `sudo tar` uit: de productiebestanden zijn root-owned en gewone `tar` kan ze niet overschrijven.
Werk met twee vaste terminalvensters: één lokale Mac-shell voor archief en upload, en één al
geopende interactieve NAS-shell voor alle controles en Docker-handelingen. Na de upload is dus
geen tweede SSH-login nodig.

```bash
git archive --format=tar.gz --output=/tmp/<release>.tar.gz <commit>
shasum -a 256 /tmp/<release>.tar.gz

ssh thact@192.168.2.20 "dd of=/tmp/<release>.tar.gz" < /tmp/<release>.tar.gz

# Voer de rest direct uit in het al geopende NAS-terminalvenster:
echo "<sha256>  /tmp/<release>.tar.gz" | sha256sum -c -
sudo tar -xzf /tmp/<release>.tar.gz -C /volume1/docker/seo-monitor/project
sudo docker compose -f compose.yaml -f compose.prod.yaml build <geraakte-services>
sudo docker compose -f compose.yaml -f compose.prod.yaml up -d <geraakte-services>
sudo docker compose -f compose.yaml -f compose.prod.yaml ps <geraakte-services>
curl --fail --silent --show-error https://seo.thact.nl/health
```

Maak niet standaard voor iedere deployment of migratie een extra databaseback-up. Maak die alleen
wanneer dit noodzakelijk is om de migratie veilig te laten verlopen of betrouwbaar te herstellen,
zoals bij datatransformatie, verwijdering, een destructieve schemawijziging of een moeilijk
omkeerbare bulkmutatie. Vermeld bij iedere release expliciet of een migratie nodig is en waarom een
nieuwe back-up wel of niet noodzakelijk is.

Voorbeeld: migratie `0034` stelde uitsluitend vier omkeerbare tabelopties op `element_locations`
in. De migratie verwijderde en herschreef geen rijen en de downgrade reset de opties. Daarom is na
de succesvolle stagingproef bewust geen nieuwe productieback-up gemaakt. Een bestaande
geverifieerde back-up bleef beschikbaar. Dit voorbeeld is geen vrijstelling voor migraties die wel
data wijzigen of moeilijk herstelbaar zijn.

## Back-up en restore

Plan `scripts/backup.sh` dagelijks via Synology Taakplanner. Stel `PROJECT_DIR`, `BACKUP_DIR` en
optioneel `BACKUP_RETENTION_DAYS` in. Kopieer back-ups ook naar een andere fysieke locatie.

Stop voor restore alle schrijvende services. Het restorescript weigert verder te gaan zolang één
van deze services nog draait. PostgreSQL en Redis blijven beschikbaar:

```bash
docker compose -f compose.yaml -f compose.prod.yaml stop \
  api worker crawl-worker-2 crawl-worker-3 integration-worker export-worker scheduler
PROJECT_DIR=/volume1/docker/seo-monitor/project ./scripts/restore.sh /pad/backup.dump
docker compose -f compose.yaml -f compose.prod.yaml up -d
```

## Rollback

1. Stop API, worker en scheduler en maak een kopie van de huidige databaseback-up.
2. Schakel Git terug naar de eerder vastgelegde release-tag of commit.
3. Herbouw de images en herstel de bij die release gemaakte databaseback-up.
4. Start alle services en controleer health, logs, crawls en exports.

Alembic-downgrades zijn niet de standaard rollbackmethode; herstel de consistente databaseback-up.

## Monitoring

Controleer periodiek:

```bash
docker compose -f compose.yaml -f compose.prod.yaml ps
docker compose -f compose.yaml -f compose.prod.yaml logs --tail=200 \
  api worker crawl-worker-2 integration-worker scheduler
docker system df
```

Configureer meldingen op een mislukte `/health`-controle en bewaak vrije schijfruimte.

Voer elementlocatie-opruiming uitsluitend tijdens een veilige crawl-drain uit, altijd voor één
website en eerst met de standaardlimiet van 50.000 rijen. Herhaal pas na controle van health,
databasebelasting en het gerapporteerde `limit_reached`:

```bash
sudo docker compose -f compose.yaml -f compose.prod.yaml exec -T api \
  python -m app.maintenance cleanup-element-locations \
  --website-id <website-uuid> --batch-size 10000 --max-rows 50000 --confirm-delete
```

De handmatige productiecleanup is op 1 augustus 2026 afgerond. In totaal zijn `6.787.671` oude,
probleemvrije elementlocaties verwijderd en `2.729.964` beschermde locaties behouden. De
eindaudit rapporteerde nul kandidaten voor vier websites en nog `4.431` voor Floris en Van Maurik;
die zijn daarna in één begrensde batch verwijderd. Vóór die laatste kleine batch rapporteerde
PostgreSQL na autovacuum en auto-analyze nul geschatte dode rijen; een handmatige `ANALYZE` was niet
nodig. Nieuwe handmatige cleanupvensters zijn alleen nodig wanneer een latere read-only audit nieuwe
kandidaten aantoont.

Vanaf migratie `0035` maakt iedere afgeronde volledige crawl automatisch een persistente
retentieoperatie. De scheduler zet deze op de queue `maintenance`; `integration-worker` verwerkt
per uitvoering maximaal 50.000 rijen en hervat resterend werk automatisch. Een actieve crawl voor
dezelfde website stelt cleanup uit. GSC- en interne-linkretentie blijven uitgesloten.

Maak of hervat alle operaties terminal-first met:

```bash
sudo docker compose -f compose.yaml -f compose.prod.yaml exec -T api \
  python -m app.maintenance retention-all
```

Gebruik de handmatige websitegebonden cleanup hierboven alleen als herstelprocedure wanneer de
persistente operatie aantoonbaar niet kan worden gebruikt.

Wanneer de terminalverbinding tijdens of na een verwijdercommando wordt onderbroken, geldt de
aanroep als mogelijk uitgevoerd. Herhaal het commando niet. Controleer eerst read-only het totale
aantal en voer `retention-audit` opnieuw uit. Start pas een nieuw, bewust benoemd venster nadat het
effect van de vorige aanroep is vastgesteld en vastgelegd.

Controleer na migratie `0034` en na ieder onderhoudsvenster de tabelinstellingen en autovacuum:

```bash
sudo docker compose -f compose.yaml -f compose.prod.yaml exec -T postgres \
  psql -U seo -d seo -P pager=off -c "
SELECT c.reloptions, s.n_live_tup, s.n_dead_tup,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
       s.last_autovacuum, s.last_autoanalyze
FROM pg_class AS c
JOIN pg_stat_user_tables AS s ON s.relid = c.oid
WHERE c.relname = 'element_locations';"
```

De verwachte opties zijn vacuüm `0.02 + 50000` en analyse `0.01 + 25000`. Gebruik geen
`VACUUM FULL` in regulier onderhoud. Beoordeel GSC-retentie afzonderlijk op rapportagebehoefte,
importstrategie en wettelijke bewaartermijn; `cleanup-element-locations` verwijdert geen GSC-data.

# Veilige crawl-drain bij updates

Na installatie van migratie `0020` wordt iedere update om actieve crawls heen uitgevoerd:

```bash
sudo docker compose -f compose.yaml -f compose.prod.yaml exec -T api \
  python -m app.maintenance pause-crawls --wait --timeout 600
```

Ga alleen verder wanneer `active=true safe=true` wordt gemeld. Bouw en herstart daarna de geraakte
services en voer de healthchecks uit. Hervat uitsluitend na een geslaagde controle:

```bash
sudo docker compose -f compose.yaml -f compose.prod.yaml exec -T api \
  python -m app.maintenance resume-crawls
```

Bij een mislukte deployment blijft de drain bewust actief. Controleer hem met
`python -m app.maintenance status` en hervat pas nadat de deployment gezond is.

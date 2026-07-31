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

De Synology-kernel ondersteunt mogelijk geen Docker `NanoCPUs`. Daarom gebruikt staging relatieve
CPU-prioriteiten (`cpu_shares`) en harde geheugenlimieten; dit is geen absolute CPU-cap. Voer builds
met `sudo nice -n 10` uit. Controleer tijdens de eerste build en proef met `docker stats` en
`docker system df` de belasting. Productie krijgt altijd voorrang; stop staging wanneer productie
merkbaar wordt beïnvloed.

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

Maak een volledige databaseback-up en drain crawls alleen wanneer een migratie of risicovolle
wijziging dit vereist. Vermeld bij iedere release expliciet of een migratie nodig is.

## Back-up en restore

Plan `scripts/backup.sh` dagelijks via Synology Taakplanner. Stel `PROJECT_DIR`, `BACKUP_DIR` en
optioneel `BACKUP_RETENTION_DAYS` in. Kopieer back-ups ook naar een andere fysieke locatie.

Stop voor restore tijdelijk API, worker en scheduler om writes te voorkomen:

```bash
docker compose -f compose.yaml -f compose.prod.yaml stop api worker scheduler
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

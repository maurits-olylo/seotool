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

## Updates

### Tijdelijke route: releasepakket via Mac

Zolang Git niet op de NAS is geïnstalleerd, wordt het releasepakket op de Mac vanaf een exacte
commit gemaakt. Leg de SHA-256 lokaal vast, upload via SSH en controleer dezelfde checksum op de NAS
voordat het pakket wordt uitgepakt. De globale crawl-drain en databaseback-up blijven verplicht.

### Doelroute: GitHub vanaf de NAS

Installeer in fase 7 Git op de NAS en configureer minimaal bevoegde GitHub-authenticatie. Controleer
de remote en actieve branch eenmalig. Productie-updates mogen daarna alleen met
`git pull --ff-only`; lokale wijzigingen in de productiemap blokkeren de deployment.

```bash
BACKUP_DIR=/volume1/docker/seo-monitor/backups ./scripts/backup.sh
git pull --ff-only
docker compose -f compose.yaml -f compose.prod.yaml build --pull
docker compose -f compose.yaml -f compose.prod.yaml run --rm api alembic upgrade head
docker compose -f compose.yaml -f compose.prod.yaml up -d
curl http://127.0.0.1:8000/health
```

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
docker compose -f compose.yaml -f compose.prod.yaml logs --tail=200 api worker scheduler
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

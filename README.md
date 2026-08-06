# SEO Monitor

Platform voor het beheren van klanten en websites, periodieke crawls, wijzigingsdetectie,
technische SEO-issues, vacaturemonitoring en CSV-/Excel-export. Excel-exporten bevatten een
afzonderlijk vacaturetabblad met lifecycle en Google for Jobs-bevindingen. De applicatie gebruikt
FastAPI, PostgreSQL en Redis/RQ en draait als acht losse Docker Compose-services.

## Architectuur

- `api`: REST API en OpenAPI-documentatie.
- `worker` en `crawl-worker-2`: maximaal twee websites gecontroleerd parallel crawlen.
- `integration-worker`: GSC-, GA4- en Bing-imports en automatische retentie op afzonderlijke
  queues.
- `export-worker`: exports op een afzonderlijke queue.
- `scheduler`: dagelijkse sitemap/light checks en wekelijkse sitecrawls.
- `postgres`: blijvende configuratie, URL-register, snapshots en issues.
- `redis`: jobqueue. Gegenereerde exports en databasegegevens staan in persistente volumes.

Zie `docs/architecture.md` voor de datastroom en databaseprincipes.

## Eerste installatie

Vereisten: Docker Engine met Compose v2 en Git. Gebruik voor lokale ontwikkeling Python 3.12.

```bash
cp .env.example .env
docker compose build
docker compose up -d postgres redis
docker compose --profile tools run --rm migrate
docker compose up -d
docker compose ps
curl http://localhost:8000/health
```

Wijzig minimaal `API_KEY`, `INITIAL_SUPERUSER_EMAIL` en `INITIAL_SUPERUSER_PASSWORD` voordat de applicatie
via een netwerk bereikbaar wordt. Het eerste interne account wordt bij de eerste start aangemaakt.
OpenAPI staat op `http://localhost:8000/docs`; technische toegang gebruikt `X-API-Key`, terwijl de
interface persoonlijke accounts en een beveiligde sessiecookie gebruikt.

## Dagelijks beheer

```bash
docker compose up -d
docker compose logs -f api worker crawl-worker-2 integration-worker scheduler
docker compose ps
docker compose down
```

`docker compose down` bewaart volumes. Gebruik niet `down -v`, tenzij alle data bewust verwijderd
mag worden.

## Development en tests

```bash
mkdir -p "$HOME/.virtualenvs"
python3.12 -m venv "$HOME/.virtualenvs/seo-tool"
source "$HOME/.virtualenvs/seo-tool/bin/activate"
pip install -e '.[dev]'
ruff check .
ruff format --check .
python -m pytest
```

Bewaar de virtuele omgeving buiten een door iCloud gesynchroniseerde projectmap. Dataless
iCloud-bestanden maken iedere nieuwe Python- en pytest-run onnodig traag.

Tests gebruiken SQLite en lokale fixtures en hebben geen internetverbinding nodig.

## Migrations en updates

```bash
docker compose --profile tools run --rm migrate alembic current
docker compose --profile tools run --rm migrate
docker compose build --pull
docker compose up -d
```

Maak niet automatisch vóór iedere productie-update een extra databaseback-up. Maak een
releasegebonden back-up alleen wanneer die noodzakelijk is om een migratie veilig te kunnen
uitvoeren of herstellen, bijvoorbeeld bij datatransformatie, destructieve schemawijziging of een
moeilijk omkeerbare bulkmutatie. Leg deze afweging per release vast. Migratie `0034` wijzigde alleen
omkeerbare tabelopties voor autovacuum, verwijderde geen data en vereiste daarom geen nieuwe
back-up. Controleer na iedere update wel `/health`, containerstatus en logs.

Migratie `0035` voegt uitsluitend de nieuwe, lege tabel `retention_operations` met indexes en
foreign keys toe. Zij wijzigt of verwijdert geen bestaande crawldata en vereist daarom geen extra
releaseback-up.

## Automatische retentie

Na iedere geslaagde of gedeeltelijk geslaagde volledige crawl worden per automatisch datatype
persistente retentieoperaties aangemaakt. De scheduler plaatst deze op de maintenancequeue. De
integration-worker verwerkt begrensde batches. Een actieve crawl voor dezelfde website laat de
operaties wachten; een onderbreking wordt vanuit PostgreSQL hervat. Issue-, taak-, verificatie- en
auditgeschiedenis blijft permanent bewaard zolang de klant bestaat.

Handmatig alle laatste operaties aanmaken of hervatten:

```bash
docker compose exec api python -m app.maintenance retention-all
```

Het actuele versieerbare beleid bewaart GSC-, GA4- en Bing-dagdata 1.098 dagen en interne
linkdetails 180 dagen, met behoud van actuele runs en bewijs. Snapshots, changes en crawlruns worden
alleen geaudit en nog niet automatisch verwijderd. Zie `docs/retention-policy.md`.

## Productie op Synology

Productie-updates worden lokaal als Git-archive gemaakt, uitsluitend via SSH-streaming naar `/tmp`
geüpload en op de NAS na checksumcontrole met `sudo tar` uitgepakt. Gebruik geen SCP en geen Git op
de NAS. Herbouw alleen de geraakte services met beide Compose-bestanden:

```bash
sudo tar -xzf /tmp/<release>.tar.gz -C /volume1/docker/seo-monitor/project
sudo docker compose -f compose.yaml -f compose.prod.yaml build <geraakte-services>
sudo docker compose -f compose.yaml -f compose.prod.yaml up -d <geraakte-services>
```

De volledige installatie-, beveiligings-, update- en rollbackprocedure staat in
`docs/deployment-synology.md`.

## Back-up en restore

```bash
./scripts/backup.sh
./scripts/restore.sh /volumepath/backups/postgres-YYYYMMDDTHHMMSSZ.dump
```

Iedere back-up wordt pas gepubliceerd nadat PostgreSQL het archief kan lezen en krijgt een
SHA-256-bestand. Restore controleert deze gegevens en weigert zolang een schrijvende service draait.
Test restores periodiek op een aparte, niet-gepubliceerde database. De scripts bewaren standaard
dertig dagen.

## Veelvoorkomende fouten

- `database unavailable`: controleer `docker compose ps postgres` en of `DATABASE_URL` dezelfde
  gebruiker, database en hetzelfde wachtwoord gebruikt als de PostgreSQL-variabelen.
- `Invalid API key`: stuur `X-API-Key` met exact de waarde uit `.env`.
- Jobs blijven `pending`: controleer Redis en `docker compose logs worker`.
- Scheduler maakt geen jobs: alleen actieve websites worden gepland; controleer schedulerlogs.
- Export ontbreekt: controleer workerlogs en het `exports_data`-volume.
- Poort 8000 bezet: wijzig `API_PORT` en gebruik `compose.prod.yaml`.

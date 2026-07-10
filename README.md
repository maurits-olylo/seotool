# SEO Monitor

Backend voor het beheren van klanten en websites, periodieke crawls, wijzigingsdetectie,
technische SEO-issues en CSV-/Excel-export. De applicatie gebruikt FastAPI, PostgreSQL en Redis/RQ
en draait als vijf losse Docker Compose-services.

## Architectuur

- `api`: REST API en OpenAPI-documentatie.
- `worker`: crawls, analyse en exports.
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
docker compose run --rm api alembic upgrade head
docker compose up -d
docker compose ps
curl http://localhost:8000/health
```

Wijzig minimaal `API_KEY` voordat de API via een netwerk bereikbaar wordt. OpenAPI staat op
`http://localhost:8000/docs`; beveiligde routes vereisen de header `X-API-Key`.

## Dagelijks beheer

```bash
docker compose up -d
docker compose logs -f api worker scheduler
docker compose ps
docker compose down
```

`docker compose down` bewaart volumes. Gebruik niet `down -v`, tenzij alle data bewust verwijderd
mag worden.

## Development en tests

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
ruff check .
ruff format --check .
python -m pytest
```

Tests gebruiken SQLite en lokale fixtures en hebben geen internetverbinding nodig.

## Migrations en updates

```bash
docker compose run --rm api alembic current
docker compose run --rm api alembic upgrade head
docker compose build --pull
docker compose up -d
```

Maak vóór iedere productie-update een back-up. Controleer daarna `/health`, containerstatus en logs.

## Productie op Synology

Gebruik beide Compose-bestanden:

```bash
docker compose -f compose.yaml -f compose.prod.yaml build
docker compose -f compose.yaml -f compose.prod.yaml run --rm api alembic upgrade head
docker compose -f compose.yaml -f compose.prod.yaml up -d
```

De volledige installatie-, beveiligings-, update- en rollbackprocedure staat in
`docs/deployment-synology.md`.

## Back-up en restore

```bash
./scripts/backup.sh
./scripts/restore.sh /volumepath/backups/postgres-YYYYMMDDTHHMMSSZ.dump
```

Test restores periodiek op een aparte installatie. De scripts bewaren standaard dertig dagen.

## Veelvoorkomende fouten

- `database unavailable`: controleer `docker compose ps postgres` en of `DATABASE_URL` dezelfde
  gebruiker, database en hetzelfde wachtwoord gebruikt als de PostgreSQL-variabelen.
- `Invalid API key`: stuur `X-API-Key` met exact de waarde uit `.env`.
- Jobs blijven `pending`: controleer Redis en `docker compose logs worker`.
- Scheduler maakt geen jobs: alleen actieve websites worden gepland; controleer schedulerlogs.
- Export ontbreekt: controleer workerlogs en het `exports_data`-volume.
- Poort 8000 bezet: wijzig `API_PORT` en gebruik `compose.prod.yaml`.


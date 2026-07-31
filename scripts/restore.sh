#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 /path/to/postgres-backup.dump" >&2
  exit 1
fi

BACKUP_FILE="$1"
PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
test -f "$BACKUP_FILE"
cd "$PROJECT_DIR"

compose() {
  if [ "${COMPOSE_TARGET:-production}" = "staging" ]; then
    docker compose --env-file .env.staging -f compose.staging.yaml "$@"
  else
    docker compose -f compose.yaml -f compose.prod.yaml "$@"
  fi
}

RUNNING_SERVICES="$(
  compose ps --status running --services
)"
RUNNING_WRITERS=""
for service in $RUNNING_SERVICES; do
  case "$service" in
    api|worker|crawl-worker-2|crawl-worker-3|integration-worker|export-worker|scheduler)
      RUNNING_WRITERS="${RUNNING_WRITERS}${RUNNING_WRITERS:+ }${service}"
      ;;
  esac
done
if [ -n "$RUNNING_WRITERS" ]; then
  echo "Restore geweigerd; stop eerst alle schrijvende services:" >&2
  printf '%s\n' "$RUNNING_WRITERS" >&2
  exit 1
fi

BACKUP_BASENAME="$(basename "$BACKUP_FILE")"
BACKUP_DIRECTORY="$(dirname "$BACKUP_FILE")"
if [ -f "$BACKUP_FILE.sha256" ]; then
  (
    cd "$BACKUP_DIRECTORY"
    if command -v sha256sum > /dev/null 2>&1; then
      sha256sum -c "$BACKUP_BASENAME.sha256"
    else
      shasum -a 256 -c "$BACKUP_BASENAME.sha256"
    fi
  )
fi
compose exec -T postgres \
  pg_restore --list < "$BACKUP_FILE" > /dev/null
compose exec -T postgres \
  pg_restore --clean --if-exists --no-owner \
  -U "${POSTGRES_USER:-seo}" -d "${POSTGRES_DB:-seo}" < "$BACKUP_FILE"
compose run --rm api alembic upgrade head
echo "Restore completed: $BACKUP_FILE"

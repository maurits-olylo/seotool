#!/bin/sh
set -eu
umask 077

PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="$BACKUP_DIR/postgres-$TIMESTAMP.dump"
TEMP_BACKUP="$BACKUP_FILE.incomplete"

compose() {
  if [ "${COMPOSE_TARGET:-production}" = "staging" ]; then
    docker compose --env-file .env.staging -f compose.staging.yaml "$@"
  else
    docker compose -f compose.yaml -f compose.prod.yaml "$@"
  fi
}

cleanup() {
  rm -f "$TEMP_BACKUP"
}
trap cleanup EXIT HUP INT TERM

mkdir -p "$BACKUP_DIR"
cd "$PROJECT_DIR"
compose exec -T postgres \
  pg_dump -U "${POSTGRES_USER:-seo}" -d "${POSTGRES_DB:-seo}" -Fc \
  > "$TEMP_BACKUP"
test -s "$TEMP_BACKUP"
compose exec -T postgres \
  pg_restore --list < "$TEMP_BACKUP" > /dev/null
mv "$TEMP_BACKUP" "$BACKUP_FILE"
(
  cd "$BACKUP_DIR"
  if command -v sha256sum > /dev/null 2>&1; then
    sha256sum "$(basename "$BACKUP_FILE")" > "$(basename "$BACKUP_FILE").sha256"
  else
    shasum -a 256 "$(basename "$BACKUP_FILE")" > "$(basename "$BACKUP_FILE").sha256"
  fi
)
find "$BACKUP_DIR" -type f \( -name 'postgres-*.dump' -o -name 'postgres-*.dump.sha256' \) \
  -mtime "+$RETENTION_DAYS" -delete
trap - EXIT HUP INT TERM
echo "Backup created and verified: $BACKUP_FILE"

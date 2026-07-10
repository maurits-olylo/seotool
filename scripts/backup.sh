#!/bin/sh
set -eu

PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$BACKUP_DIR"
cd "$PROJECT_DIR"
docker compose -f compose.yaml -f compose.prod.yaml exec -T postgres \
  pg_dump -U "${POSTGRES_USER:-seo}" -d "${POSTGRES_DB:-seo}" -Fc \
  > "$BACKUP_DIR/postgres-$TIMESTAMP.dump"
find "$BACKUP_DIR" -type f -name 'postgres-*.dump' -mtime "+$RETENTION_DAYS" -delete
echo "Backup created: $BACKUP_DIR/postgres-$TIMESTAMP.dump"

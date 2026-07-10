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
docker compose -f compose.yaml -f compose.prod.yaml exec -T postgres \
  pg_restore --clean --if-exists --no-owner \
  -U "${POSTGRES_USER:-seo}" -d "${POSTGRES_DB:-seo}" < "$BACKUP_FILE"
docker compose -f compose.yaml -f compose.prod.yaml run --rm api alembic upgrade head
echo "Restore completed: $BACKUP_FILE"

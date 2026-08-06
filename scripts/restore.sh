#!/bin/sh
set -eu
umask 077

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 /path/to/seo-monitor-<target>-<timestamp>.tar.enc" >&2
  exit 1
fi

BACKUP_FILE="$1"
PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
BACKUP_KEY_FILE="${BACKUP_KEY_FILE:-}"
TARGET="${COMPOSE_TARGET:-production}"
PBKDF2_ITERATIONS=600000
[ "${APP_ENV:-}" = "test" ] && PBKDF2_ITERATIONS="${BACKUP_TEST_PBKDF2_ITERATIONS:-600000}"
test -f "$BACKUP_FILE"
test -f "$BACKUP_FILE.sha256"
if [ -z "$BACKUP_KEY_FILE" ] || [ ! -f "$BACKUP_KEY_FILE" ]; then
  echo "BACKUP_KEY_FILE must point to the recovery key file" >&2
  exit 1
fi

compose() {
  if [ "$TARGET" = "staging" ]; then
    docker compose --env-file .env.staging -f compose.staging.yaml "$@"
  elif [ "$TARGET" = "production" ]; then
    docker compose -f compose.yaml -f compose.prod.yaml "$@"
  else
    echo "Unsupported COMPOSE_TARGET: $TARGET" >&2
    exit 1
  fi
}

verify_sha256() {
  file="$1"
  checksum="$2"
  directory="$(dirname "$file")"
  basename="$(basename "$checksum")"
  (cd "$directory" && if command -v sha256sum > /dev/null 2>&1; then sha256sum -c "$basename"; else shasum -a 256 -c "$basename"; fi)
}

cd "$PROJECT_DIR"
RUNNING_SERVICES="$(compose ps --status running --services)"
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

verify_sha256 "$BACKUP_FILE" "$BACKUP_FILE.sha256"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/seo-monitor-restore.XXXXXX")"
cleanup() { rm -rf "$WORK_DIR"; }
trap cleanup EXIT HUP INT TERM

openssl enc -d -aes-256-cbc -pbkdf2 -iter "$PBKDF2_ITERATIONS" -md sha256 \
  -pass "file:$BACKUP_KEY_FILE" -in "$BACKUP_FILE" -out "$WORK_DIR/bundle.tar"
tar -tf "$WORK_DIR/bundle.tar" > /dev/null
tar -xf "$WORK_DIR/bundle.tar" -C "$WORK_DIR"
for component in manifest.txt postgres.dump exports.tar recovery.env privacy-deletions.jsonl; do
  test -f "$WORK_DIR/$component"
  test -f "$WORK_DIR/$component.sha256"
  verify_sha256 "$WORK_DIR/$component" "$WORK_DIR/$component.sha256"
done
grep -q '^format_version=1$' "$WORK_DIR/manifest.txt"
grep -q "^compose_target=$TARGET$" "$WORK_DIR/manifest.txt"
tar -tf "$WORK_DIR/exports.tar" > /dev/null
compose exec -T postgres pg_restore --list < "$WORK_DIR/postgres.dump" > /dev/null

compose exec -T postgres pg_restore --clean --if-exists --no-owner \
  -U "${POSTGRES_USER:-seo}" -d "${POSTGRES_DB:-seo}" < "$WORK_DIR/postgres.dump"
compose --profile tools run --rm migrate
if [ "${RESTORE_PRIVACY_LEDGER_IF_EMPTY:-false}" = "true" ]; then
  compose run --rm --no-deps -T -v "$WORK_DIR:/restore:ro" api python -c \
    'from pathlib import Path; source=Path("/restore/privacy-deletions.jsonl"); target=Path("/app/privacy-ledger/deletions.jsonl"); target.parent.mkdir(parents=True, exist_ok=True); (not target.exists() or target.stat().st_size == 0) and target.write_bytes(source.read_bytes())'
fi
compose run --rm --no-deps -T api python -m app.maintenance reapply-privacy-deletions
compose run --rm --no-deps -T -v "$WORK_DIR:/restore:ro" api python -c \
  'import pathlib, shutil, tarfile; root=pathlib.Path("/app/exports"); [shutil.rmtree(p) if p.is_dir() else p.unlink() for p in list(root.iterdir())]; tarfile.open("/restore/exports.tar").extractall("/app")'

if [ "${RESTORE_ENVIRONMENT:-false}" = "true" ]; then
  destination="$PROJECT_DIR/.env"
  [ "$TARGET" = "staging" ] && destination="$PROJECT_DIR/.env.staging"
  temporary="$destination.restore"
  cp "$WORK_DIR/recovery.env" "$temporary"
  chmod 600 "$temporary"
  mv "$temporary" "$destination"
fi

echo "Restore completed and validated: $BACKUP_FILE"
echo "Keep writers stopped until the current privacy-deletion register has been reapplied."

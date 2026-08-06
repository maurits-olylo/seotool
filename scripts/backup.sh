#!/bin/sh
set -eu
umask 077

PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
BACKUP_KEY_FILE="${BACKUP_KEY_FILE:-}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="${COMPOSE_TARGET:-production}"
ENV_FILE="${BACKUP_ENV_FILE:-$PROJECT_DIR/.env}"
PBKDF2_ITERATIONS=600000
[ "${APP_ENV:-}" = "test" ] && PBKDF2_ITERATIONS="${BACKUP_TEST_PBKDF2_ITERATIONS:-600000}"

if [ "$TARGET" = "staging" ]; then
  [ -n "${BACKUP_ENV_FILE:-}" ] || ENV_FILE="$PROJECT_DIR/.env.staging"
elif [ "$TARGET" != "production" ]; then
  echo "Unsupported COMPOSE_TARGET: $TARGET" >&2
  exit 1
fi

if [ -z "$BACKUP_KEY_FILE" ] || [ ! -f "$BACKUP_KEY_FILE" ]; then
  echo "BACKUP_KEY_FILE must point to an existing key file" >&2
  exit 1
fi
if [ ! -f "$ENV_FILE" ]; then
  echo "Environment file not found: $ENV_FILE" >&2
  exit 1
fi

file_mode() {
  stat -c '%a' "$1" 2>/dev/null || stat -f '%Lp' "$1"
}

case "$(file_mode "$BACKUP_KEY_FILE")" in
  600|400) ;;
  *) echo "BACKUP_KEY_FILE must have mode 0600 or 0400" >&2; exit 1 ;;
esac
case "$(file_mode "$ENV_FILE")" in
  600|400) ;;
  *) echo "Environment file must have mode 0600 or 0400" >&2; exit 1 ;;
esac

compose() {
  if [ "$TARGET" = "staging" ]; then
    docker compose --env-file .env.staging -f compose.staging.yaml "$@"
  else
    docker compose -f compose.yaml -f compose.prod.yaml "$@"
  fi
}

sha256_file() {
  if command -v sha256sum > /dev/null 2>&1; then
    sha256sum "$1"
  else
    shasum -a 256 "$1"
  fi
}

mkdir -p "$BACKUP_DIR"
WORK_DIR="$(mktemp -d "$BACKUP_DIR/.backup-$TIMESTAMP.XXXXXX")"
PLAIN_ARCHIVE="$BACKUP_DIR/.seo-monitor-$TARGET-$TIMESTAMP.tar.incomplete"
BACKUP_FILE="$BACKUP_DIR/seo-monitor-$TARGET-$TIMESTAMP.tar.enc"

cleanup() {
  rm -rf "$WORK_DIR"
  rm -f "$PLAIN_ARCHIVE" "$BACKUP_FILE.incomplete"
}
trap cleanup EXIT HUP INT TERM

cd "$PROJECT_DIR"
compose exec -T postgres \
  pg_dump -U "${POSTGRES_USER:-seo}" -d "${POSTGRES_DB:-seo}" -Fc \
  > "$WORK_DIR/postgres.dump"
test -s "$WORK_DIR/postgres.dump"
compose exec -T postgres pg_restore --list < "$WORK_DIR/postgres.dump" > /dev/null

compose exec -T api python -c \
  'import sys, tarfile; archive=tarfile.open(fileobj=sys.stdout.buffer, mode="w|"); archive.add("/app/exports", arcname="exports"); archive.close()' \
  > "$WORK_DIR/exports.tar"
tar -tf "$WORK_DIR/exports.tar" > /dev/null
compose exec -T api python -c \
  'from pathlib import Path; import sys; path=Path("/app/privacy-ledger/deletions.jsonl"); sys.stdout.buffer.write(path.read_bytes() if path.exists() else b"")' \
  > "$WORK_DIR/privacy-deletions.jsonl"

cp "$ENV_FILE" "$WORK_DIR/recovery.env"
chmod 600 "$WORK_DIR/recovery.env"
GIT_COMMIT="$(git -C "$PROJECT_DIR" rev-parse HEAD 2>/dev/null || printf 'not-available')"
cat > "$WORK_DIR/manifest.txt" <<EOF
format_version=1
created_at_utc=$TIMESTAMP
compose_target=$TARGET
git_commit=$GIT_COMMIT
database=${POSTGRES_DB:-seo}
includes=postgres.dump,exports.tar,recovery.env,privacy-deletions.jsonl
encryption=openssl-aes-256-cbc-pbkdf2-sha256
privacy_restore_rule=apply-current-deletion-register-before-service-start
EOF

(
  cd "$WORK_DIR"
  sha256_file postgres.dump > postgres.dump.sha256
  sha256_file exports.tar > exports.tar.sha256
  sha256_file recovery.env > recovery.env.sha256
  sha256_file privacy-deletions.jsonl > privacy-deletions.jsonl.sha256
  sha256_file manifest.txt > manifest.txt.sha256
)

tar -cf "$PLAIN_ARCHIVE" -C "$WORK_DIR" \
  manifest.txt manifest.txt.sha256 postgres.dump postgres.dump.sha256 \
  exports.tar exports.tar.sha256 recovery.env recovery.env.sha256 \
  privacy-deletions.jsonl privacy-deletions.jsonl.sha256
openssl enc -aes-256-cbc -salt -pbkdf2 -iter "$PBKDF2_ITERATIONS" -md sha256 \
  -pass "file:$BACKUP_KEY_FILE" -in "$PLAIN_ARCHIVE" -out "$BACKUP_FILE.incomplete"
openssl enc -d -aes-256-cbc -pbkdf2 -iter "$PBKDF2_ITERATIONS" -md sha256 \
  -pass "file:$BACKUP_KEY_FILE" -in "$BACKUP_FILE.incomplete" | tar -tf - > /dev/null
mv "$BACKUP_FILE.incomplete" "$BACKUP_FILE"
(
  cd "$BACKUP_DIR"
  sha256_file "$(basename "$BACKUP_FILE")" > "$(basename "$BACKUP_FILE").sha256"
  ln -sfn "$(basename "$BACKUP_FILE")" "seo-monitor-$TARGET-latest.tar.enc"
  ln -sfn "$(basename "$BACKUP_FILE").sha256" \
    "seo-monitor-$TARGET-latest.tar.enc.sha256"
)
rm -f "$PLAIN_ARCHIVE"

find "$BACKUP_DIR" -type f \
  \( -name 'seo-monitor-*.tar.enc' -o -name 'seo-monitor-*.tar.enc.sha256' \) \
  -mtime "+$RETENTION_DAYS" -delete
trap - EXIT HUP INT TERM
rm -rf "$WORK_DIR"
echo "Encrypted backup created and verified: $BACKUP_FILE"

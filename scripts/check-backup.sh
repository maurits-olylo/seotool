#!/bin/sh
set -eu
umask 077

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 /path/to/seo-monitor-<target>-<timestamp>.tar.enc" >&2
  exit 1
fi

BACKUP_FILE="$1"
BACKUP_KEY_FILE="${BACKUP_KEY_FILE:-}"
MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-30}"
PBKDF2_ITERATIONS=600000
[ "${APP_ENV:-}" = "test" ] && PBKDF2_ITERATIONS="${BACKUP_TEST_PBKDF2_ITERATIONS:-600000}"
test -f "$BACKUP_FILE"
test -f "$BACKUP_FILE.sha256"
test -n "$BACKUP_KEY_FILE"
test -f "$BACKUP_KEY_FILE"

now="$(date +%s)"
modified="$(stat -c '%Y' "$BACKUP_FILE" 2>/dev/null || stat -f '%m' "$BACKUP_FILE")"
age_hours="$(( (now - modified) / 3600 ))"
if [ "$age_hours" -gt "$MAX_AGE_HOURS" ]; then
  echo "Backup check failed: newest bundle is ${age_hours} hours old" >&2
  exit 1
fi

directory="$(dirname "$BACKUP_FILE")"
checksum="$(basename "$BACKUP_FILE").sha256"
(
  cd "$directory"
  if command -v sha256sum > /dev/null 2>&1; then
    sha256sum -c "$checksum"
  else
    shasum -a 256 -c "$checksum"
  fi
)
openssl enc -d -aes-256-cbc -pbkdf2 -iter "$PBKDF2_ITERATIONS" -md sha256 \
  -pass "file:$BACKUP_KEY_FILE" -in "$BACKUP_FILE" | tar -tf - > /dev/null
echo "Backup is recent, checksum-valid, decryptable and archive-readable"

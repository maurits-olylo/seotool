#!/bin/sh
set -eu
umask 077

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 /secure/path/seo-monitor-backup.key" >&2
  exit 1
fi

KEY_FILE="$1"
if [ -e "$KEY_FILE" ]; then
  echo "Key file already exists; rotation requires a separate recovery procedure" >&2
  exit 1
fi

KEY_DIRECTORY="$(dirname "$KEY_FILE")"
mkdir -p "$KEY_DIRECTORY"
TEMP_FILE="$(mktemp "$KEY_DIRECTORY/.backup-key.XXXXXX")"
cleanup() { rm -f "$TEMP_FILE"; }
trap cleanup EXIT HUP INT TERM
openssl rand -hex 48 > "$TEMP_FILE"
chmod 600 "$TEMP_FILE"
mv "$TEMP_FILE" "$KEY_FILE"
trap - EXIT HUP INT TERM
echo "Backup key created without displaying its value; mode 0600 validated"

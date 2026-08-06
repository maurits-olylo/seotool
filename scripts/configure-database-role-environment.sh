#!/bin/sh
set -eu
umask 077

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 /path/to/.env database_name" >&2
  exit 1
fi

ENV_FILE="$1"
DATABASE_NAME="$2"
test -f "$ENV_FILE"
command -v openssl > /dev/null 2>&1

API_PASSWORD="$(openssl rand -hex 32)"
CRAWLER_PASSWORD="$(openssl rand -hex 32)"
INTEGRATION_PASSWORD="$(openssl rand -hex 32)"
EXPORT_PASSWORD="$(openssl rand -hex 32)"
SCHEDULER_PASSWORD="$(openssl rand -hex 32)"
TEMP_FILE="$(mktemp "${ENV_FILE}.tmp.XXXXXX")"

cleanup() {
  rm -f "$TEMP_FILE"
}
trap cleanup EXIT HUP INT TERM

awk \
  -v database_name="$DATABASE_NAME" \
  -v api="$API_PASSWORD" \
  -v crawler="$CRAWLER_PASSWORD" \
  -v integration="$INTEGRATION_PASSWORD" \
  -v export_password="$EXPORT_PASSWORD" \
  -v scheduler="$SCHEDULER_PASSWORD" '
function write_once(key, value) {
  if (!written[key]) {
    print key "=" value
    written[key] = 1
  }
}
/^DB_API_PASSWORD=/ { write_once("DB_API_PASSWORD", api); next }
/^DB_CRAWLER_PASSWORD=/ { write_once("DB_CRAWLER_PASSWORD", crawler); next }
/^DB_INTEGRATION_PASSWORD=/ { write_once("DB_INTEGRATION_PASSWORD", integration); next }
/^DB_EXPORT_PASSWORD=/ { write_once("DB_EXPORT_PASSWORD", export_password); next }
/^DB_SCHEDULER_PASSWORD=/ { write_once("DB_SCHEDULER_PASSWORD", scheduler); next }
/^API_DATABASE_URL=/ {
  write_once("API_DATABASE_URL", "postgresql+psycopg://seo_api:" api "@postgres:5432/" database_name)
  next
}
/^CRAWLER_DATABASE_URL=/ {
  write_once("CRAWLER_DATABASE_URL", "postgresql+psycopg://seo_crawler:" crawler "@postgres:5432/" database_name)
  next
}
/^INTEGRATION_DATABASE_URL=/ {
  write_once("INTEGRATION_DATABASE_URL", "postgresql+psycopg://seo_integration:" integration "@postgres:5432/" database_name)
  next
}
/^EXPORT_DATABASE_URL=/ {
  write_once("EXPORT_DATABASE_URL", "postgresql+psycopg://seo_export:" export_password "@postgres:5432/" database_name)
  next
}
/^SCHEDULER_DATABASE_URL=/ {
  write_once("SCHEDULER_DATABASE_URL", "postgresql+psycopg://seo_scheduler:" scheduler "@postgres:5432/" database_name)
  next
}
{ print }
END {
  write_once("DB_API_PASSWORD", api)
  write_once("DB_CRAWLER_PASSWORD", crawler)
  write_once("DB_INTEGRATION_PASSWORD", integration)
  write_once("DB_EXPORT_PASSWORD", export_password)
  write_once("DB_SCHEDULER_PASSWORD", scheduler)
  write_once("API_DATABASE_URL", "postgresql+psycopg://seo_api:" api "@postgres:5432/" database_name)
  write_once("CRAWLER_DATABASE_URL", "postgresql+psycopg://seo_crawler:" crawler "@postgres:5432/" database_name)
  write_once("INTEGRATION_DATABASE_URL", "postgresql+psycopg://seo_integration:" integration "@postgres:5432/" database_name)
  write_once("EXPORT_DATABASE_URL", "postgresql+psycopg://seo_export:" export_password "@postgres:5432/" database_name)
  write_once("SCHEDULER_DATABASE_URL", "postgresql+psycopg://seo_scheduler:" scheduler "@postgres:5432/" database_name)
}
' "$ENV_FILE" > "$TEMP_FILE"

mv "$TEMP_FILE" "$ENV_FILE"
chmod 600 "$ENV_FILE"
trap - EXIT HUP INT TERM
unset API_PASSWORD CRAWLER_PASSWORD INTEGRATION_PASSWORD EXPORT_PASSWORD SCHEDULER_PASSWORD
echo "Database role environment configured without displaying secrets"

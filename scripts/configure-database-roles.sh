#!/bin/sh
set -eu

: "${DB_API_PASSWORD:?DB_API_PASSWORD is required}"
: "${DB_CRAWLER_PASSWORD:?DB_CRAWLER_PASSWORD is required}"
: "${DB_INTEGRATION_PASSWORD:?DB_INTEGRATION_PASSWORD is required}"
: "${DB_EXPORT_PASSWORD:?DB_EXPORT_PASSWORD is required}"
: "${DB_SCHEDULER_PASSWORD:?DB_SCHEDULER_PASSWORD is required}"

PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR"

if [ "${COMPOSE_TARGET:-production}" = "staging" ]; then
  set -- docker compose --env-file .env.staging -f compose.staging.yaml
else
  set -- docker compose -f compose.yaml -f compose.prod.yaml
fi

"$@" exec -T postgres psql \
  -v ON_ERROR_STOP=1 \
  -v database_name="${POSTGRES_DB:-seo}" \
  -v api_password="$DB_API_PASSWORD" \
  -v crawler_password="$DB_CRAWLER_PASSWORD" \
  -v integration_password="$DB_INTEGRATION_PASSWORD" \
  -v export_password="$DB_EXPORT_PASSWORD" \
  -v scheduler_password="$DB_SCHEDULER_PASSWORD" \
  -U "${POSTGRES_USER:-seo}" -d "${POSTGRES_DB:-seo}" \
  < scripts/database-roles.sql

echo "Database roles and grants configured"

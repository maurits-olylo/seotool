#!/bin/sh
set -eu

PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR"

if [ "${COMPOSE_TARGET:-production}" = "staging" ]; then
  set -- docker compose --env-file .env.staging -f compose.staging.yaml
else
  set -- docker compose -f compose.yaml -f compose.prod.yaml
fi

"$@" --profile tools run --rm database-roles

echo "Database roles and grants configured"

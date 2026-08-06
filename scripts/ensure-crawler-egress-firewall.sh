#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ATTEMPT=1
MAX_ATTEMPTS="${CRAWLER_FIREWALL_MAX_ATTEMPTS:-12}"

while [ "$ATTEMPT" -le "$MAX_ATTEMPTS" ]; do
  if "$SCRIPT_DIR/crawler-egress-firewall.sh" apply; then
    exit 0
  fi
  if [ "$ATTEMPT" -eq "$MAX_ATTEMPTS" ]; then
    break
  fi
  sleep 10
  ATTEMPT=$((ATTEMPT + 1))
done

echo "Crawler egress firewall could not be applied after Docker startup" >&2
exit 1

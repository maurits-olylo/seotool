#!/bin/sh
set -eu

NETWORK_NAME="${CRAWLER_EGRESS_NETWORK_NAME:-seo-monitor-crawler-egress}"
PROJECT_NAME="${CRAWLER_EGRESS_PROJECT_NAME:-seo-monitor}"

case "$NETWORK_NAME" in
  *[!a-zA-Z0-9_.-]*|"")
    echo "Crawler egress network refused: invalid network name" >&2
    exit 1
    ;;
esac
case "$PROJECT_NAME" in
  *[!a-zA-Z0-9_.-]*|"")
    echo "Crawler egress network refused: invalid Compose project name" >&2
    exit 1
    ;;
esac

if ! docker network inspect "$NETWORK_NAME" > /dev/null 2>&1; then
  docker network create \
    --driver bridge \
    --label "com.docker.compose.project=$PROJECT_NAME" \
    --label com.docker.compose.network=crawler-egress \
    "$NETWORK_NAME" > /dev/null
fi

DRIVER="$(docker network inspect "$NETWORK_NAME" --format '{{.Driver}}')"
INTERNAL="$(docker network inspect "$NETWORK_NAME" --format '{{.Internal}}')"
IPV6_ENABLED="$(docker network inspect "$NETWORK_NAME" --format '{{.EnableIPv6}}')"
if [ "$DRIVER" != "bridge" ] || [ "$INTERNAL" != "false" ] || [ "$IPV6_ENABLED" != "false" ]; then
  echo "Crawler egress network refused: expected external IPv4-only bridge network" >&2
  exit 1
fi

echo "Crawler egress network ready"

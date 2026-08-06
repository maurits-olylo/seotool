#!/bin/sh
set -eu

NETWORK_NAME="${CRAWLER_EGRESS_NETWORK_NAME:-seo-monitor-crawler-egress}"
CHAIN_NAME="${CRAWLER_EGRESS_CHAIN_NAME:-SEO-CRAWLER-EGRESS}"
MODE="${1:-apply}"

if [ "$MODE" != "apply" ] && [ "$MODE" != "check" ]; then
  echo "Usage: $0 [apply|check]" >&2
  exit 1
fi
case "$CHAIN_NAME" in
  *[!A-Z0-9-]*|"")
    echo "Crawler egress refused: invalid firewall chain name" >&2
    exit 1
    ;;
esac
if [ "$(id -u)" -ne 0 ]; then
  echo "Run this script as root" >&2
  exit 1
fi

IPV6_ENABLED="$(docker network inspect "$NETWORK_NAME" --format '{{.EnableIPv6}}')"
if [ "$IPV6_ENABLED" != "false" ]; then
  echo "Crawler egress refused: Docker IPv6 must be disabled" >&2
  exit 1
fi

SUBNET="$(
  docker network inspect "$NETWORK_NAME" \
    --format '{{range .IPAM.Config}}{{if .Subnet}}{{.Subnet}}{{end}}{{end}}'
)"
if [ -z "$SUBNET" ]; then
  echo "Crawler egress refused: IPv4 subnet is unavailable" >&2
  exit 1
fi

BLOCKED_DESTINATIONS="
0.0.0.0/8
10.0.0.0/8
100.64.0.0/10
127.0.0.0/8
169.254.0.0/16
172.16.0.0/12
192.0.0.0/24
192.0.2.0/24
192.168.0.0/16
198.18.0.0/15
198.51.100.0/24
203.0.113.0/24
224.0.0.0/4
240.0.0.0/4
"

check_rules() {
  LINK_POSITION="$(
    iptables -S DOCKER-USER | awk -v chain="$CHAIN_NAME" \
      '$1 == "-A" { position += 1; if ($NF == chain) { print position; exit } }'
  )"
  RETURN_POSITION="$(
    iptables -S DOCKER-USER | awk \
      '$1 == "-A" { position += 1; if ($NF == "RETURN") { print position; exit } }'
  )"
  test -n "$LINK_POSITION"
  test -n "$RETURN_POSITION"
  test "$LINK_POSITION" -lt "$RETURN_POSITION"
  for destination in $BLOCKED_DESTINATIONS; do
    iptables -C "$CHAIN_NAME" -s "$SUBNET" -d "$destination" \
      -j DROP > /dev/null 2>&1
  done
  iptables -C "$CHAIN_NAME" -s "$SUBNET" -j RETURN > /dev/null 2>&1
}

if [ "$MODE" = "check" ]; then
  if check_rules; then
    echo "Crawler egress firewall active"
    exit 0
  fi
  echo "Crawler egress firewall missing or stale" >&2
  exit 1
fi

iptables -nL "$CHAIN_NAME" > /dev/null 2>&1 || iptables -N "$CHAIN_NAME"
iptables -F "$CHAIN_NAME"
for destination in $BLOCKED_DESTINATIONS; do
  iptables -A "$CHAIN_NAME" -s "$SUBNET" -d "$destination" \
    -j DROP
done
iptables -A "$CHAIN_NAME" -s "$SUBNET" -j RETURN
while iptables -C DOCKER-USER -j "$CHAIN_NAME" > /dev/null 2>&1; do
  iptables -D DOCKER-USER -j "$CHAIN_NAME"
done
iptables -I DOCKER-USER 1 -j "$CHAIN_NAME"

check_rules
echo "Crawler egress firewall applied"

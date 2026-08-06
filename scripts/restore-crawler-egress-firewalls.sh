#!/bin/sh
set -eu

PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
export PATH

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

CRAWLER_EGRESS_NETWORK_NAME=seo-monitor-crawler-egress \
CRAWLER_EGRESS_PROJECT_NAME=seo-monitor \
CRAWLER_EGRESS_CHAIN_NAME=SEO-CRAWLER-EGRESS \
  "$SCRIPT_DIR/ensure-crawler-egress-firewall.sh"

CRAWLER_EGRESS_NETWORK_NAME=seo-monitor-staging-crawler-egress \
CRAWLER_EGRESS_PROJECT_NAME=seo-monitor-staging \
CRAWLER_EGRESS_CHAIN_NAME=SEO-CRAWLER-STAGING \
  "$SCRIPT_DIR/ensure-crawler-egress-firewall.sh"

echo "Crawler egress firewalls restored"

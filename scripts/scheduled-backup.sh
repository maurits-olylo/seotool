#!/bin/sh
set -eu
umask 077

PROJECT_DIR="${PROJECT_DIR:-/volume1/docker/seo-monitor/project}"
BACKUP_DIR="${BACKUP_DIR:-/volume1/docker/seo-monitor/backups-encrypted}"
BACKUP_KEY_FILE="${BACKUP_KEY_FILE:-/volume1/docker/seo-monitor/secrets/production-backup.key}"
OFFSITE_BACKUP_CONFIG_FILE="${OFFSITE_BACKUP_CONFIG_FILE:-/volume1/docker/seo-monitor/secrets/offsite-backup.env}"
LOCK_DIR="${BACKUP_LOCK_DIR:-/tmp/seo-monitor-scheduled-backup.lock}"
WRITERS_STOPPED=false
DRAIN_ACTIVE=false

if [ -f "$OFFSITE_BACKUP_CONFIG_FILE" ]; then
  config_mode="$(stat -c '%a' "$OFFSITE_BACKUP_CONFIG_FILE")"
  case "$config_mode" in
    600|400) ;;
    *) echo "Off-site backup config must have mode 0600 or 0400" >&2; exit 1 ;;
  esac
  set -a
  # shellcheck disable=SC1090 -- the protected deployment file is deliberately external to Git
  . "$OFFSITE_BACKUP_CONFIG_FILE"
  set +a
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "Scheduled backup must run as root" >&2
  exit 1
fi
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "Scheduled backup refused: another backup lock is active" >&2
  exit 1
fi

compose() {
  docker compose -f compose.yaml -f compose.prod.yaml "$@"
}

cleanup() {
  exit_status="$?"
  trap - EXIT HUP INT TERM
  set +e
  cd "$PROJECT_DIR" 2>/dev/null
  if [ "$WRITERS_STOPPED" = "true" ]; then
    compose up -d integration-worker export-worker scheduler
    sleep 40
  fi
  if [ "$DRAIN_ACTIVE" = "true" ]; then
    compose exec -T api python -m app.maintenance resume-crawls
  fi
  rmdir "$LOCK_DIR" 2>/dev/null
  exit "$exit_status"
}
trap cleanup EXIT HUP INT TERM

cd "$PROJECT_DIR"
compose exec -T api python -m app.maintenance pause-crawls --wait --timeout 600
DRAIN_ACTIVE=true
compose stop integration-worker export-worker scheduler
WRITERS_STOPPED=true

PROJECT_DIR="$PROJECT_DIR" \
BACKUP_DIR="$BACKUP_DIR" \
BACKUP_KEY_FILE="$BACKUP_KEY_FILE" \
BACKUP_ENV_FILE="$PROJECT_DIR/.env" \
COMPOSE_TARGET=production \
POSTGRES_USER="${POSTGRES_USER:-seo}" \
POSTGRES_DB="${POSTGRES_DB:-seo}" \
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}" \
"$PROJECT_DIR/scripts/backup.sh"

BACKUP_KEY_FILE="$BACKUP_KEY_FILE" \
BACKUP_MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-30}" \
"$PROJECT_DIR/scripts/check-backup.sh" \
"$BACKUP_DIR/seo-monitor-production-latest.tar.enc"

if [ "${S3_BACKUP_ENABLED:-false}" = "true" ]; then
  python3 "$PROJECT_DIR/scripts/offsite-backup.py" upload \
    "$BACKUP_DIR/seo-monitor-production-latest.tar.enc"
fi

compose up -d integration-worker export-worker scheduler
WRITERS_STOPPED=false
sleep 40
compose ps integration-worker export-worker scheduler
curl --fail --silent --show-error http://127.0.0.1:8000/health
compose exec -T api python -m app.maintenance resume-crawls
DRAIN_ACTIVE=false
echo "Scheduled encrypted local and off-site backup completed successfully"

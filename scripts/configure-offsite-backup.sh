#!/bin/sh
set -eu
umask 077

SECRETS_DIR="${OFFSITE_BACKUP_SECRETS_DIR:-/volume1/docker/seo-monitor/secrets}"
CONFIG_FILE="$SECRETS_DIR/offsite-backup.env"
CREDENTIALS_FILE="$SECRETS_DIR/scaleway-backup-upload.credentials"

if [ "$(id -u)" -ne 0 ]; then
  echo "Off-site backup configuration must run as root" >&2
  exit 1
fi
if [ -e "$CONFIG_FILE" ] || [ -e "$CREDENTIALS_FILE" ]; then
  echo "Off-site backup configuration already exists; refusing to overwrite" >&2
  exit 1
fi

mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"
config_tmp="$(mktemp "$SECRETS_DIR/.offsite-backup.env.XXXXXX")"
credentials_tmp="$(mktemp "$SECRETS_DIR/.scaleway-backup-upload.XXXXXX")"

cleanup() {
  stty echo 2>/dev/null || true
  rm -f "$config_tmp" "$credentials_tmp"
}
trap cleanup EXIT HUP INT TERM

printf 'Scaleway upload access key (hidden): ' >&2
stty -echo
IFS= read -r access_key
printf '\nScaleway upload secret key (hidden): ' >&2
IFS= read -r secret_key
stty echo
printf '\n' >&2

case "$access_key" in
  ""|*[!A-Za-z0-9_-]*) echo "Invalid access key format" >&2; exit 1 ;;
esac
if [ "${#secret_key}" -lt 20 ]; then
  echo "Secret key is unexpectedly short" >&2
  exit 1
fi

cat > "$credentials_tmp" <<EOF
AWS_ACCESS_KEY_ID=$access_key
AWS_SECRET_ACCESS_KEY=$secret_key
EOF
cat > "$config_tmp" <<EOF
S3_BACKUP_ENABLED=true
S3_BACKUP_ENDPOINT=https://s3.fr-par.scw.cloud
S3_BACKUP_REGION=fr-par
S3_BACKUP_BUCKET=thactual
S3_BACKUP_PREFIX=seo-monitor/production
S3_BACKUP_OBJECT_LOCK_DAYS=30
S3_BACKUP_CREDENTIALS_FILE=$CREDENTIALS_FILE
EOF
chmod 600 "$config_tmp" "$credentials_tmp"
mv "$credentials_tmp" "$CREDENTIALS_FILE"
mv "$config_tmp" "$CONFIG_FILE"
trap - EXIT HUP INT TERM
echo "Off-site backup upload configuration installed with mode 0600"

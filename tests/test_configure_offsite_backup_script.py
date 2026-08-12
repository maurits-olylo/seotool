from pathlib import Path


def test_offsite_configuration_hides_and_protects_credentials() -> None:
    project_root = Path(__file__).resolve().parents[1]
    script = (project_root / "scripts/configure-offsite-backup.sh").read_text()

    assert 'if [ "$(id -u)" -ne 0 ]' in script
    assert 'stty -echo' in script
    assert 'stty echo' in script
    assert 'if [ -e "$CONFIG_FILE" ] || [ -e "$CREDENTIALS_FILE" ]' in script
    assert 'chmod 600 "$config_tmp" "$credentials_tmp"' in script
    assert 'S3_BACKUP_ENDPOINT=https://s3.fr-par.scw.cloud' in script
    assert 'S3_BACKUP_BUCKET=thactual' in script
    assert 'S3_BACKUP_OBJECT_LOCK_DAYS=30' in script
    assert "echo \"$access_key\"" not in script
    assert "echo \"$secret_key\"" not in script

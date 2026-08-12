from pathlib import Path


def test_scheduled_backup_restores_services_and_drain_on_failure() -> None:
    project_root = Path(__file__).resolve().parents[1]
    script = (project_root / "scripts/scheduled-backup.sh").read_text()

    assert 'if [ "$(id -u)" -ne 0 ]' in script
    assert 'mkdir "$LOCK_DIR"' in script
    assert "pause-crawls --wait --timeout 600" in script
    assert "compose stop integration-worker export-worker scheduler" in script
    assert 'trap cleanup EXIT HUP INT TERM' in script
    assert 'if [ "$WRITERS_STOPPED" = "true" ]' in script
    assert 'if [ "$DRAIN_ACTIVE" = "true" ]' in script
    assert "resume-crawls" in script
    assert "scripts/check-backup.sh" in script
    assert 'OFFSITE_BACKUP_CONFIG_FILE="${OFFSITE_BACKUP_CONFIG_FILE:-' in script
    assert 'if [ "${S3_BACKUP_ENABLED:-false}" = "true" ]' in script
    assert 'scripts/offsite-backup.py" upload' in script
    assert "curl --fail --silent --show-error http://127.0.0.1:8000/health" in script

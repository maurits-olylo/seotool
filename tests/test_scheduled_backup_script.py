from pathlib import Path


def test_scheduled_backup_restores_services_and_drain_on_failure() -> None:
    project_root = Path(__file__).resolve().parents[1]
    script = (project_root / "scripts/scheduled-backup.sh").read_text()

    assert 'if [ "$(id -u)" -ne 0 ]' in script
    assert 'mkdir "$LOCK_DIR"' in script
    assert "pause-crawls --wait --timeout 600" in script
    assert "compose stop integration-worker maintenance-worker export-worker scheduler" in script
    assert "trap cleanup EXIT HUP INT TERM" in script
    assert 'if [ "$WRITERS_STOPPED" = "true" ]' in script
    assert 'if [ "$DRAIN_ACTIVE" = "true" ]' in script
    assert "resume-crawls" in script
    assert "scripts/check-backup.sh" in script
    assert 'OFFSITE_BACKUP_CONFIG_FILE="${OFFSITE_BACKUP_CONFIG_FILE:-' in script
    assert 'if [ "${S3_BACKUP_ENABLED:-false}" = "true" ]' in script
    assert 'scripts/offsite-backup.py" upload' in script
    assert "curl --fail --silent --show-error http://127.0.0.1:8000/health" in script


def test_pause_timeout_attempts_resume_and_keeps_failure(tmp_path) -> None:
    import os
    import subprocess

    binaries = tmp_path / "bin"
    binaries.mkdir()
    log = tmp_path / "calls.log"
    (binaries / "id").write_text("#!/bin/sh\necho 0\n")
    (binaries / "docker").write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALL_LOG"\n'
        'case "$*" in *pause-crawls*) exit 7 ;; esac\nexit 0\n'
    )
    for executable in binaries.iterdir():
        executable.chmod(0o755)
    root = Path(__file__).resolve().parents[1]
    lock = tmp_path / "backup.lock"
    result = subprocess.run(
        ["sh", str(root / "scripts/scheduled-backup.sh")],
        env={
            **os.environ,
            "PATH": f"{binaries}:{os.environ['PATH']}",
            "PROJECT_DIR": str(tmp_path),
            "OFFSITE_BACKUP_CONFIG_FILE": str(tmp_path / "absent.env"),
            "BACKUP_LOCK_DIR": str(lock),
            "CALL_LOG": str(log),
        },
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 7
    calls = log.read_text().splitlines()
    assert len(calls) == 2
    assert "pause-crawls" in calls[0]
    assert "resume-crawls" in calls[1]
    assert not lock.exists()

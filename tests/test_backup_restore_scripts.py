from __future__ import annotations

import os
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]


def _fake_docker(tmp_path: Path, *, running_writers: str = "") -> dict[str, str]:
    executable = tmp_path / "docker"
    executable.write_text(
        """#!/bin/sh
set -eu
printf '%s\\n' "$*" >> "$FAKE_DOCKER_LOG"
case "$*" in
  *"ps --status running --services"*)
    printf '%s' "${FAKE_RUNNING_WRITERS:-}"
    ;;
  *"pg_dump"*)
    printf 'fake-postgres-archive'
    ;;
  *"privacy-ledger/deletions.jsonl"*)
    printf ''
    ;;
  *"exec -T api python -c"*)
    tar -cf - --files-from /dev/null
    ;;
  *"pg_restore --list"*)
    cat > /dev/null
    ;;
esac
"""
    )
    executable.chmod(0o755)
    return {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "FAKE_DOCKER_LOG": str(tmp_path / "docker.log"),
        "FAKE_RUNNING_WRITERS": running_writers,
    }


def _secret_file(path: Path, content: str) -> Path:
    path.write_text(content)
    path.chmod(0o600)
    return path


def _backup_environment(tmp_path: Path, *, target: str = "production") -> dict[str, str]:
    env = _fake_docker(tmp_path)
    env.update(
        {
            "PROJECT_DIR": str(PROJECT_DIR),
            "BACKUP_DIR": str(tmp_path / "backups"),
            "BACKUP_KEY_FILE": str(
                _secret_file(tmp_path / "backup.key", "test-only-recovery-passphrase")
            ),
            "BACKUP_ENV_FILE": str(
                _secret_file(tmp_path / ".env.test", "TOKEN_ENCRYPTION_KEY=test-only\n")
            ),
            "COMPOSE_TARGET": target,
            "APP_ENV": "test",
            "BACKUP_TEST_PBKDF2_ITERATIONS": "1000",
        }
    )
    return env


def test_backup_creates_verified_encrypted_bundle_and_checksum(tmp_path: Path) -> None:
    env = _backup_environment(tmp_path)
    result = subprocess.run(
        ["sh", str(PROJECT_DIR / "scripts/backup.sh")],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    archives = [
        path
        for path in (tmp_path / "backups").glob("seo-monitor-production-*.tar.enc")
        if not path.is_symlink()
    ]
    assert len(archives) == 1
    assert archives[0].read_bytes().startswith(b"Salted__")
    assert Path(f"{archives[0]}.sha256").is_file()
    latest = tmp_path / "backups" / "seo-monitor-production-latest.tar.enc"
    assert latest.resolve() == archives[0].resolve()
    assert Path(f"{latest}.sha256").resolve() == Path(f"{archives[0]}.sha256").resolve()
    assert not list((tmp_path / "backups").glob("*.incomplete"))


def test_backup_rejects_insecure_key_permissions(tmp_path: Path) -> None:
    env = _backup_environment(tmp_path)
    Path(env["BACKUP_KEY_FILE"]).chmod(0o644)

    result = subprocess.run(
        ["sh", str(PROJECT_DIR / "scripts/backup.sh")],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode != 0
    assert "mode 0600 or 0400" in result.stderr


def test_restore_refuses_while_writer_is_running(tmp_path: Path) -> None:
    backup = tmp_path / "bundle.tar.enc"
    backup.write_bytes(b"encrypted-placeholder")
    Path(f"{backup}.sha256").write_text("unused\n")
    env = _fake_docker(tmp_path, running_writers="api\nexport-worker\n")
    env.update(
        {
            "PROJECT_DIR": str(PROJECT_DIR),
            "BACKUP_KEY_FILE": str(
                _secret_file(tmp_path / "backup.key", "test-only-recovery-passphrase")
            ),
        }
    )

    result = subprocess.run(
        ["sh", str(PROJECT_DIR / "scripts/restore.sh"), str(backup)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 1
    assert "Restore geweigerd" in result.stderr
    assert "api" in result.stderr
    assert "export-worker" in result.stderr
    assert "pg_restore --clean" not in (tmp_path / "docker.log").read_text()


def test_restore_requires_checksum(tmp_path: Path) -> None:
    backup = tmp_path / "bundle.tar.enc"
    backup.write_bytes(b"encrypted-placeholder")
    env = _fake_docker(tmp_path)
    env.update(
        {
            "PROJECT_DIR": str(PROJECT_DIR),
            "BACKUP_KEY_FILE": str(
                _secret_file(tmp_path / "backup.key", "test-only-recovery-passphrase")
            ),
        }
    )

    result = subprocess.run(
        ["sh", str(PROJECT_DIR / "scripts/restore.sh"), str(backup)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode != 0
    assert not (tmp_path / "docker.log").exists()


def test_staging_target_uses_only_staging_compose(tmp_path: Path) -> None:
    env = _backup_environment(tmp_path, target="staging")
    env.update({"POSTGRES_USER": "seo_staging", "POSTGRES_DB": "seo_staging"})

    result = subprocess.run(
        ["sh", str(PROJECT_DIR / "scripts/backup.sh")],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    log = (tmp_path / "docker.log").read_text()
    assert "--env-file .env.staging -f compose.staging.yaml" in log
    assert "compose.prod.yaml" not in log

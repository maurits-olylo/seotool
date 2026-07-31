from __future__ import annotations

import hashlib
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
  *"pg_restore --list"*)
    cat > /dev/null
    ;;
esac
"""
    )
    executable.chmod(0o755)
    log_file = tmp_path / "docker.log"
    return {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "FAKE_DOCKER_LOG": str(log_file),
        "FAKE_RUNNING_WRITERS": running_writers,
    }


def test_backup_creates_verified_archive_and_checksum(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    env = _fake_docker(tmp_path)
    env.update(
        {
            "PROJECT_DIR": str(PROJECT_DIR),
            "BACKUP_DIR": str(backup_dir),
        }
    )

    result = subprocess.run(
        ["sh", str(PROJECT_DIR / "scripts/backup.sh")],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    archives = list(backup_dir.glob("postgres-*.dump"))
    assert len(archives) == 1
    assert archives[0].read_bytes() == b"fake-postgres-archive"
    assert archives[0].with_suffix(".dump.sha256").is_file()
    assert not list(backup_dir.glob("*.incomplete"))


def test_restore_refuses_while_writer_is_running(tmp_path: Path) -> None:
    backup = tmp_path / "postgres.dump"
    backup.write_bytes(b"fake-postgres-archive")
    env = _fake_docker(tmp_path, running_writers="api\nexport-worker\n")
    env["PROJECT_DIR"] = str(PROJECT_DIR)

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
    log = (tmp_path / "docker.log").read_text()
    assert "pg_restore --clean" not in log


def test_restore_checks_checksum_and_archive_before_restore(tmp_path: Path) -> None:
    backup = tmp_path / "postgres.dump"
    content = b"fake-postgres-archive"
    backup.write_bytes(content)
    checksum = hashlib.sha256(content).hexdigest()
    backup.with_suffix(".dump.sha256").write_text(f"{checksum}  {backup.name}\n")
    env = _fake_docker(tmp_path)
    env["PROJECT_DIR"] = str(PROJECT_DIR)

    result = subprocess.run(
        ["sh", str(PROJECT_DIR / "scripts/restore.sh"), str(backup)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    log = (tmp_path / "docker.log").read_text()
    assert "pg_restore --list" in log
    assert "pg_restore --clean --if-exists --no-owner" in log
    assert "run --rm api alembic upgrade head" in log


def test_staging_target_uses_only_staging_compose(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    env = _fake_docker(tmp_path)
    env.update(
        {
            "PROJECT_DIR": str(PROJECT_DIR),
            "BACKUP_DIR": str(backup_dir),
            "COMPOSE_TARGET": "staging",
            "POSTGRES_USER": "seo_staging",
            "POSTGRES_DB": "seo_staging",
        }
    )

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

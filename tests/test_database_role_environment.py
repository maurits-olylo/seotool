from __future__ import annotations

import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]


def test_database_role_environment_is_atomic_unique_and_url_safe(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_ENV=production\n"
        "DB_API_PASSWORD=old\n"
        "DB_API_PASSWORD=duplicate\n"
        "API_DATABASE_URL=old\n"
    )

    result = subprocess.run(
        [
            "sh",
            str(PROJECT_DIR / "scripts/configure-database-role-environment.sh"),
            str(env_file),
            "seo_test",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        "Database role environment configured without displaying secrets"
    )
    values = dict(
        line.split("=", 1)
        for line in env_file.read_text().splitlines()
        if "=" in line
    )
    roles = ("API", "CRAWLER", "INTEGRATION", "EXPORT", "SCHEDULER")
    passwords = []
    for role in roles:
        password = values[f"DB_{role}_PASSWORD"]
        passwords.append(password)
        assert len(password) == 64
        assert set(password) <= set("0123456789abcdef")
        username = role.lower() if role != "INTEGRATION" else "integration"
        assert values[f"{role}_DATABASE_URL"] == (
            f"postgresql+psycopg://seo_{username}:{password}@postgres:5432/seo_test"
        )
    assert len(set(passwords)) == len(passwords)
    assert env_file.stat().st_mode & 0o777 == 0o600
    assert env_file.read_text().count("DB_API_PASSWORD=") == 1

from pathlib import Path


def test_sensor_migration_is_linear_additive_and_role_scoped() -> None:
    root = Path(__file__).resolve().parents[1]
    migration = (root / "alembic/versions/0061_sensor_measurement_foundation.py").read_text()
    roles = (root / "scripts/database-roles.sql").read_text()

    assert 'revision: str = "0061"' in migration
    assert 'down_revision: str | None = "0060"' in migration
    for table in (
        "sensor_manifests",
        "sensor_outcome_definitions",
        "sensor_daily_page_metrics",
        "sensor_measurement_states",
    ):
        assert f'"{table}"' in migration
        assert table in roles

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


def _load_migration() -> ModuleType:
    path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "0034_tune_element_locations_autovacuum.py"
    )
    spec = spec_from_file_location("migration_0034", path)
    assert spec is not None
    assert spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_element_locations_autovacuum_migration_is_reversible() -> None:
    migration = _load_migration()

    with patch.object(migration.op, "execute") as execute:
        migration.upgrade()
        migration.downgrade()

    upgrade_sql = str(execute.call_args_list[0].args[0])
    downgrade_sql = str(execute.call_args_list[1].args[0])
    assert "ALTER TABLE element_locations SET" in upgrade_sql
    assert "autovacuum_vacuum_scale_factor = 0.02" in upgrade_sql
    assert "autovacuum_vacuum_threshold = 50000" in upgrade_sql
    assert "autovacuum_analyze_scale_factor = 0.01" in upgrade_sql
    assert "autovacuum_analyze_threshold = 25000" in upgrade_sql
    assert "ALTER TABLE element_locations RESET" in downgrade_sql

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import patch


def test_repeatable_render_migration_drops_and_restores_unique_constraint() -> None:
    path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "0060_repeatable_render_observations.py"
    )
    spec = spec_from_file_location("migration_0060", path)
    assert spec and spec.loader
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)

    with (
        patch.object(migration.op, "drop_constraint") as drop_constraint,
        patch.object(migration.op, "create_unique_constraint") as create_constraint,
    ):
        migration.upgrade()
        migration.downgrade()

    drop_constraint.assert_called_once_with(
        "render_observations_source_snapshot_id_key",
        "render_observations",
        type_="unique",
    )
    create_constraint.assert_called_once_with(
        "render_observations_source_snapshot_id_key",
        "render_observations",
        ["source_snapshot_id"],
    )

import ast
from pathlib import Path


def test_release_14_phase_c_fixture_is_synthetic_offline_and_cleans_up() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts/accept-release-14-phase-c-staging.py").read_text()
    ast.parse(source)

    assert "release-14-first-crawl.example.test" in source
    assert 'SimpleNamespace(app_env="test")' in source
    assert '"redis_jobs": 0' in source
    assert '"idempotent_first_crawl": True' in source
    assert "finally:" in source
    assert "db.delete(client)" in source
    assert "release-14-phase-c-fixture-clean" in source

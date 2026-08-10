import ast
from pathlib import Path


def test_phase_e_fixture_is_synthetic_and_always_cleans_up() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts/accept-release-13-phase-e-staging.py").read_text()
    ast.parse(source)

    assert "sensor-phase-e.example.test" in source
    assert 'assert state.status == "reliable"' in source
    assert 'effect.evidence[0]["basis"] == "observed_correlation"' in source
    assert "finally:" in source
    assert "db.delete(stored_client)" in source
    assert 'print("release-13-phase-e-fixture-clean")' in source

import ast
from pathlib import Path


def test_release_14_phase_a_fixture_is_synthetic_and_cleans_up() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts/accept-release-14-phase-a-staging.py").read_text()
    ast.parse(source)

    assert "release-14-onboarding.example.test" in source
    assert "token not in verification.token_hash" in source
    assert '"crawl_jobs": 0' in source
    assert "finally:" in source
    assert "db.delete(client)" in source
    assert "release-14-phase-a-fixture-clean" in source

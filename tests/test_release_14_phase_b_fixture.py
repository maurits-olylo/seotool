import ast
from pathlib import Path


def test_release_14_phase_b_fixture_is_synthetic_and_cleans_up() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts/accept-release-14-phase-b-staging.py").read_text()
    ast.parse(source)

    assert "release-14-verification.example.test" in source
    assert "renew_website_verification_file" in source
    assert '"crawl_jobs": 0' in source
    assert '"guided_ui": True' in source
    assert "finally:" in source
    assert "db.delete(client)" in source
    assert "release-14-phase-b-fixture-clean" in source

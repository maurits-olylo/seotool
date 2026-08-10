import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_phase_d_fixture_is_synthetic_same_origin_and_checks_order() -> None:
    source = (ROOT / "scripts/accept-release-13-phase-d-staging.py").read_text(encoding="utf-8")
    ast.parse(source)

    assert 'FIXTURE_URL = "https://sensor.example.test/offerte"' in source
    assert '"page_view"' in source
    assert '"element_exposure"' in source
    assert '"element_interaction"' in source
    assert '"process_start"' in source
    assert '"process_success"' in source
    assert "assert actions == EXPECTED_ACTIONS" in source
    assert "assert cookies == []" in source
    assert "assert duplicate_success_rejected is True" in source
    assert "example.com" not in source

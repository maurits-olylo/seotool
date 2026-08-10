import ast
import runpy
from pathlib import Path

from app.db.session import SessionLocal  # noqa: F401 - enables the isolated database fixture


def test_phase_f_fixture_covers_closed_boundary_abuse_and_deletion() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts/accept-release-13-phase-f-staging.py").read_text()
    ast.parse(source)

    for check in (
        "personal_data",
        "browser_trust_escalation",
        "oversized_batch",
        "replayed_event",
    ):
        assert check in source
    assert "public_sensor_routes" in source
    assert "apply_privacy_deletions" in source
    assert "deletion_replay_idempotent" in source
    assert "synthetic_data_clean" in source


def test_phase_f_fixture_executes_against_isolated_database(capsys) -> None:  # type: ignore[no-untyped-def]
    root = Path(__file__).resolve().parents[1]
    namespace = runpy.run_path(str(root / "scripts/accept-release-13-phase-f-staging.py"))

    namespace["main"]()

    output = capsys.readouterr().out
    assert "release_13_phase_f_staging_ok" in output
    assert "synthetic_data_clean" in output


def test_phase_f_browser_acceptance_uses_pinned_bounded_artifact() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts/accept-release-13-phase-f-browser.py").read_text()
    ast.parse(source)

    assert "MAXIMUM_CLIENT_BYTES" in source
    assert 'lock["sha256"]' in source
    assert "measure-sensor-client.py" in source
    assert "measure-sensor-browser.py" in source
    assert "accept-release-13-phase-d-staging.py" in source
    assert "release-13-phase-f-browser-ok" in source

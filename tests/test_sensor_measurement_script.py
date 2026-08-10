import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_browser_measurement_is_bounded_and_synthetic() -> None:
    path = ROOT / "scripts" / "measure-sensor-browser.py"
    source = path.read_text(encoding="utf-8")
    ast.parse(source)

    assert "RUNS = 20" in source
    assert 'FIXTURE_URL = "https://sensor.example.test/fixture"' in source
    assert '"execution_ms_p75_max": 25' in source
    assert '"tracking_requests_max": 2' in source
    assert '"largest_batch_min": 5' in source
    assert '"long_tasks_at_least_50ms_max": 0' in source
    assert '"largest_batch_min"' in source
    assert '"tracking_methods"' in source
    assert "example.com" not in source

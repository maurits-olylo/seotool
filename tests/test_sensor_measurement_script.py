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
    assert '"sensor_attributable_long_tasks_max": 0' in source
    assert '"baseline_long_tasks_at_least_50ms"' in source
    assert '"sensor_long_tasks_at_least_50ms"' in source
    assert '"largest_batch_min"' in source
    assert '"tracking_methods"' in source
    assert 'pair_orders.append("baseline_first")' in source
    assert 'pair_orders.append("sensor_first")' in source
    assert '"pair_order": "alternating_ab_ba"' in source
    assert '"long_task_pairs"' in source
    assert "example.com" not in source

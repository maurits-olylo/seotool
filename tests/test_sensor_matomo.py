import json
import subprocess
from pathlib import Path

from app.services.sensor_matomo import observation_to_matomo_command
from tests.test_sensor_contract import _observation

ROOT = Path(__file__).resolve().parents[1]


def test_adapter_maps_canonical_observations_at_provider_edge() -> None:
    page = observation_to_matomo_command(
        _observation(
            name="page_view",
            subject=None,
            value={},
            trust="browser",
            priority="important",
        )
    )
    exposure = observation_to_matomo_command(
        _observation(
            name="element_exposure",
            subject="primary_cta",
            value={"visibility_bucket": "half_1s"},
            trust="browser",
            priority="optional",
        )
    )
    success = observation_to_matomo_command(_observation())

    assert page.name == "queueRequest"
    assert page.arguments == ("e_c=thactual_sensor&e_a=page_view&e_n=2026-08-10.1%3Apage",)
    assert exposure.name == "queueRequest"
    assert exposure.arguments == (
        "e_c=thactual_sensor&e_a=element_exposure&e_n=2026-08-10.1%3Aprimary_cta",
    )
    assert success.name == "queueRequest"
    assert success.arguments == (
        "e_c=thactual_sensor&e_a=process_success&e_n=2026-08-10.1%3Aquote_form",
    )


def test_bootstrap_uses_same_origin_cookieless_bounded_configuration() -> None:
    script = (ROOT / "sensor" / "bootstrap.js").read_text(encoding="utf-8")

    assert '["disableCookies"]' in script
    assert '["disablePerformanceTracking"]' in script
    assert '["setTrackerUrl", "/thactual/observe"]' in script
    assert "trackAllContentImpressions" not in script
    assert "trackVisibleContentImpressions" not in script
    assert "enableLinkTracking" not in script
    assert "MutationObserver" not in script


def test_bootstrap_maps_only_allowlisted_events_in_node() -> None:
    runner = """
const fs = require('fs');
const vm = require('vm');
const context = {window: {location: {pathname: '/offerte'}}, URLSearchParams};
vm.createContext(context);
vm.runInContext(fs.readFileSync('sensor/bootstrap.js', 'utf8'), context);
const sensor = context.window.ThactualSensorBootstrap.initialize({
  schemaVersion: '1', manifestVersion: 'v1', siteId: '7'
});
sensor.observe({
  name: 'element_exposure',
  subject: 'primary_cta',
  value: {visibility_bucket: 'half_1s'}
});
sensor.observe({name: 'process_start', subject: 'quote_form', value: {}});
let rejected = false;
try {
  sensor.observe({name: 'unknown', subject: 'anything', value: {}});
} catch (_) {
  rejected = true;
}
process.stdout.write(JSON.stringify({queue: context.window._paq, rejected}));
"""
    completed = subprocess.run(
        ["node", "-e", runner], cwd=ROOT, check=True, capture_output=True, text=True
    )
    result = json.loads(completed.stdout)

    assert result["rejected"] is True
    assert ["setTrackerUrl", "/thactual/observe"] in result["queue"]
    assert [
        "queueRequest",
        "e_c=thactual_sensor&e_a=element_exposure&e_n=v1%3Aprimary_cta",
    ] in result["queue"]
    assert [
        "queueRequest",
        "e_c=thactual_sensor&e_a=process_start&e_n=v1%3Aquote_form",
    ] in result["queue"]


def test_pinned_client_measurement_is_reproducible(tmp_path: Path) -> None:
    lock = json.loads((ROOT / "sensor" / "matomo-client.lock.json").read_text(encoding="utf-8"))
    assert lock["version"] == "5.10.0"
    assert lock["vendored"] is False
    assert lock["gzip_bytes"] < 50_000

    wrong_artifact = tmp_path / "matomo.js"
    wrong_artifact.write_text("not the pinned client", encoding="utf-8")
    completed = subprocess.run(
        [
            str(ROOT / ".venv" / "bin" / "python"),
            "scripts/measure-sensor-client.py",
            wrong_artifact,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "checksum does not match" in completed.stderr

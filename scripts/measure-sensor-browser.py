#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from statistics import median
from typing import Any

RUNS = 20
FIXTURE_URL = "https://sensor.example.test/fixture"
FIXTURE_HTML = """<!doctype html><html><head><meta charset="utf-8"></head>
<body><main><button data-thactual="primary-cta">Start</button></main></body></html>"""


def percentile_75(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * 0.75))]


def observe_long_tasks(page: Any) -> None:
    page.evaluate(
        """
        window.__sensorLongTasks = [];
        new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) window.__sensorLongTasks.push(entry.duration);
        }).observe({entryTypes: ['longtask']});
        """
    )


def measure_baseline(browser: Any) -> dict[str, Any]:
    context = browser.new_context(service_workers="block")
    page = context.new_page()
    page.route(
        "**/*",
        lambda route: route.fulfill(status=200, content_type="text/html", body=FIXTURE_HTML),
    )
    page.goto(FIXTURE_URL, wait_until="domcontentloaded")
    observe_long_tasks(page)
    page.wait_for_timeout(3000)
    long_tasks = page.evaluate("window.__sensorLongTasks")
    context.close()
    return {"long_tasks": [round(float(duration), 3) for duration in long_tasks]}


def measure_once(browser: Any, matomo_source: str, bootstrap_source: str) -> dict[str, Any]:
    context = browser.new_context(service_workers="block")
    page = context.new_page()
    requests: list[dict[str, int | str]] = []

    def record_tracking_request(request: Any) -> None:
        if "/thactual/observe" not in request.url:
            return
        batch_size = 0
        try:
            payload = json.loads(request.post_data or "")
            if isinstance(payload, dict) and isinstance(payload.get("requests"), list):
                batch_size = len(payload["requests"])
        except Exception:  # noqa: BLE001 - diagnostics must not inspect or expose invalid payloads
            pass
        requests.append({"method": request.method, "batch_size": batch_size})

    page.route(
        "**/*",
        lambda route: route.fulfill(
            status=200,
            content_type="text/html" if route.request.url == FIXTURE_URL else "text/plain",
            body=FIXTURE_HTML if route.request.url == FIXTURE_URL else "ok",
        ),
    )
    page.on("request", record_tracking_request)
    page.goto(FIXTURE_URL, wait_until="domcontentloaded")
    observe_long_tasks(page)
    execution_ms = page.evaluate(
        """([bootstrap, matomo]) => {
          const started = performance.now();
          const add = (source) => {
            const script = document.createElement('script');
            script.textContent = source;
            document.head.appendChild(script);
          };
          add(bootstrap);
          window.ThactualSensorBootstrap.initialize({
            schemaVersion: '1', manifestVersion: 'v1', siteId: '1', measurementAllowed: true
          });
          window.ThactualSensor.observe({name: 'page_view', value: {}});
          window.ThactualSensor.observe({
            name: 'element_exposure', subject: 'primary_cta',
            value: {visibility_bucket: 'half_1s'}
          });
          window.ThactualSensor.observe({
            name: 'element_interaction', subject: 'primary_cta',
            value: {interaction_type: 'click'}
          });
          window.ThactualSensor.observe({
            name: 'process_start', subject: 'quote_form', value: {}
          });
          window.ThactualSensor.observe({
            name: 'process_success', subject: 'quote_form',
            value: {evidence_strength: 'application_event'}
          });
          add(matomo);
          return performance.now() - started;
        }""",
        [bootstrap_source, matomo_source],
    )
    page.wait_for_timeout(3000)
    long_tasks = page.evaluate("window.__sensorLongTasks")
    context.close()
    return {
        "execution_ms": round(float(execution_ms), 3),
        "long_tasks": [round(float(duration), 3) for duration in long_tasks],
        "tracking_requests": len(requests),
        "tracking_methods": sorted({str(request["method"]) for request in requests}),
        "largest_batch": max((int(request["batch_size"]) for request in requests), default=0),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure the synthetic Sensor browser spike")
    parser.add_argument("matomo_client", type=Path)
    parser.add_argument("--runs", type=int, default=RUNS)
    arguments = parser.parse_args()
    if arguments.runs < RUNS:
        raise SystemExit(f"At least {RUNS} runs are required")

    from playwright.sync_api import sync_playwright

    matomo_source = arguments.matomo_client.read_text(encoding="utf-8")
    bootstrap_source = (Path(__file__).resolve().parents[1] / "sensor/bootstrap.js").read_text(
        encoding="utf-8"
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        baseline_results = []
        results = []
        for _ in range(arguments.runs):
            baseline_results.append(measure_baseline(browser))
            results.append(measure_once(browser, matomo_source, bootstrap_source))
        browser.close()

    execution = [float(result["execution_ms"]) for result in results]
    requests = [int(result["tracking_requests"]) for result in results]
    methods = sorted({method for result in results for method in result["tracking_methods"]})
    batch_sizes = [int(result["largest_batch"]) for result in results]
    baseline_long_tasks = [
        duration for result in baseline_results for duration in result["long_tasks"]
    ]
    sensor_long_tasks = [duration for result in results for duration in result["long_tasks"]]
    attributable_long_tasks = 0
    for baseline, sensor in zip(baseline_results, results, strict=True):
        baseline_max = max(baseline["long_tasks"], default=0)
        sensor_max = max(sensor["long_tasks"], default=0)
        if sensor_max >= 50 and (baseline_max < 50 or sensor_max > baseline_max + 5):
            attributable_long_tasks += 1
    summary = {
        "runs": len(results),
        "execution_ms_median": round(median(execution), 3),
        "execution_ms_p75": round(percentile_75(execution), 3),
        "tracking_requests_max": max(requests),
        "tracking_methods": methods,
        "largest_batch_min": min(batch_sizes),
        "baseline_long_tasks_at_least_50ms": sum(
            duration >= 50 for duration in baseline_long_tasks
        ),
        "sensor_long_tasks_at_least_50ms": sum(duration >= 50 for duration in sensor_long_tasks),
        "baseline_long_task_max_ms": max(baseline_long_tasks, default=0),
        "sensor_long_task_max_ms": max(sensor_long_tasks, default=0),
        "sensor_attributable_long_tasks": attributable_long_tasks,
        "budget": {
            "execution_ms_p75_max": 25,
            "tracking_requests_max": 2,
            "largest_batch_min": 5,
            "sensor_attributable_long_tasks_max": 0,
        },
    }
    summary["within_budget"] = (
        summary["execution_ms_p75"] <= 25
        and summary["tracking_requests_max"] <= 2
        and summary["largest_batch_min"] >= 5
        and summary["sensor_attributable_long_tasks"] == 0
    )
    print(json.dumps(summary, sort_keys=True))
    if not summary["within_budget"]:
        raise SystemExit("Synthetic Sensor browser spike exceeds the pilot budget")


if __name__ == "__main__":
    main()

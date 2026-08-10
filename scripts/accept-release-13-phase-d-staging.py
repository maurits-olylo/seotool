#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

FIXTURE_URL = "https://sensor.example.test/offerte"
FIXTURE_HTML = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<main>
  <button type="button" data-thactual="primary-cta">Start aanvraag</button>
  <form data-thactual="quote-form"><button type="submit">Verzenden</button></form>
</main>
</body></html>"""
EXPECTED_ACTIONS = [
    "page_view",
    "element_exposure",
    "element_interaction",
    "process_start",
    "process_success",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Accept the Release 13 phase-D Sensor fixture")
    parser.add_argument("matomo_client", type=Path)
    arguments = parser.parse_args()

    from playwright.sync_api import sync_playwright

    root = Path(__file__).resolve().parents[1]
    bootstrap = (root / "sensor/bootstrap.js").read_text(encoding="utf-8")
    matomo = arguments.matomo_client.read_text(encoding="utf-8")
    captured: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(service_workers="block")
        page = context.new_page()

        def route_request(route: Any) -> None:
            request = route.request
            if "/thactual/observe" in request.url:
                captured.append(
                    {
                        "url": request.url,
                        "method": request.method,
                        "payload": json.loads(request.post_data or "{}"),
                    }
                )
                route.fulfill(status=204, body="")
                return
            route.fulfill(status=200, content_type="text/html", body=FIXTURE_HTML)

        page.route("**/*", route_request)
        page.goto(FIXTURE_URL, wait_until="domcontentloaded")
        page.evaluate(
            """([bootstrap, matomo]) => {
              const add = (source) => {
                const script = document.createElement('script');
                script.textContent = source;
                document.head.appendChild(script);
              };
              add(bootstrap);
              window.__loadMatomo = () => add(matomo);
              window.ThactualSensorBootstrap.initialize({
                schemaVersion: '1',
                manifestVersion: '2026-08-10.1',
                siteId: '1',
                measurementAllowed: true,
                manifest: {
                  schema_version: '1',
                  manifest_version: '2026-08-10.1',
                  page_match: '/offerte',
                  expires_at: new Date(Date.now() + 86400000).toISOString(),
                  observations: [
                    {key: 'primary_cta', kind: 'exposure', locator: 'primary-cta'},
                    {key: 'quote_form', kind: 'process', locator: 'quote-form'}
                  ]
                }
              });
            }""",
            [bootstrap, matomo],
        )
        page.wait_for_timeout(1200)
        page.click('[data-thactual="primary-cta"]')
        page.dispatch_event('[data-thactual="quote-form"]', "submit")
        page.dispatch_event('[data-thactual="quote-form"]', "submit")
        page.evaluate("window.ThactualSensor.processSuccess('quote_form', 'application_event')")
        duplicate_success_rejected = page.evaluate(
            """() => {
              try {
                window.ThactualSensor.processSuccess('quote_form', 'application_event');
                return false;
              } catch (_) {
                return true;
              }
            }"""
        )
        page.evaluate("window.__loadMatomo()")
        page.wait_for_timeout(3000)

        cookies = context.cookies()
        context.close()
        browser.close()

    assert len(captured) == 1, f"expected one tracking request, got {len(captured)}"
    request = captured[0]
    assert request["method"] == "POST"
    assert urlparse(request["url"]).netloc == "sensor.example.test"
    requests = request["payload"].get("requests")
    assert isinstance(requests, list) and len(requests) == len(EXPECTED_ACTIONS)
    actions = [parse_qs(str(item).lstrip("?")).get("e_a", [None])[0] for item in requests]
    assert actions == EXPECTED_ACTIONS
    assert cookies == []
    assert duplicate_success_rejected is True
    print(
        {
            "status": "release_13_phase_d_staging_ok",
            "same_origin": True,
            "cookies": 0,
            "requests": 1,
            "observations": len(requests),
            "ordered_actions": actions,
            "duplicate_success_rejected": True,
        }
    )


if __name__ == "__main__":
    main()

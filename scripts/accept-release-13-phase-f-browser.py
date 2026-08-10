#!/usr/bin/env python3
import hashlib
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "sensor" / "matomo-client.lock.json"
MAXIMUM_CLIENT_BYTES = 100_000


def main() -> None:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    request = urllib.request.Request(
        str(lock["source"]), headers={"User-Agent": "Thactual-Sensor-Acceptance/1.0"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - pinned checksum
        client = response.read(MAXIMUM_CLIENT_BYTES + 1)
    assert len(client) <= MAXIMUM_CLIENT_BYTES
    assert len(client) == int(lock["bytes"])
    assert hashlib.sha256(client).hexdigest() == lock["sha256"]

    with tempfile.NamedTemporaryFile(suffix=".js") as artifact:
        artifact.write(client)
        artifact.flush()
        for script in (
            "measure-sensor-client.py",
            "measure-sensor-browser.py",
            "accept-release-13-phase-d-staging.py",
        ):
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / script), artifact.name],
                check=True,
            )
    print("release-13-phase-f-browser-ok")


if __name__ == "__main__":
    main()

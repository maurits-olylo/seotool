#!/usr/bin/env python3
import argparse
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "sensor" / "matomo-client.lock.json"
BOOTSTRAP_PATH = ROOT / "sensor" / "bootstrap.js"
TOTAL_COMPRESSED_BUDGET = 50_000


def artifact_metrics(path: Path) -> dict[str, int | str]:
    content = path.read_bytes()
    return {
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "gzip_bytes": len(gzip.compress(content, compresslevel=9, mtime=0)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the pinned Sensor/Matomo client budget")
    parser.add_argument("matomo_client", type=Path)
    arguments = parser.parse_args()

    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    matomo = artifact_metrics(arguments.matomo_client)
    bootstrap = artifact_metrics(BOOTSTRAP_PATH)
    if matomo["sha256"] != lock["sha256"]:
        raise SystemExit("Matomo client checksum does not match the pinned artifact")

    compressed_total = int(matomo["gzip_bytes"]) + int(bootstrap["gzip_bytes"])
    result = {
        "matomo": matomo,
        "bootstrap": bootstrap,
        "compressed_total": compressed_total,
        "compressed_budget": TOTAL_COMPRESSED_BUDGET,
        "within_budget": compressed_total <= TOTAL_COMPRESSED_BUDGET,
    }
    print(json.dumps(result, sort_keys=True))
    if not result["within_budget"]:
        raise SystemExit("Sensor client exceeds the compressed performance budget")


if __name__ == "__main__":
    main()

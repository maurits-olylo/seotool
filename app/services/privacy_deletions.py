from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.sensor import (
    SensorDailyPageMetric,
    SensorManifest,
    SensorMeasurementState,
    SensorOutcomeDefinition,
)
from app.models.website import Website

SUPPORTED_ENTITY_TYPES = {"client", "website"}
SENSOR_WEBSITE_MODELS = (
    SensorDailyPageMetric,
    SensorMeasurementState,
    SensorOutcomeDefinition,
    SensorManifest,
)


def privacy_deletion_ledger_path() -> Path:
    return Path(
        os.environ.get(
            "PRIVACY_DELETION_LEDGER_FILE",
            "/app/privacy-ledger/deletions.jsonl",
        )
    )


def record_privacy_deletion(entity_type: str, entity_id: UUID) -> None:
    if entity_type not in SUPPORTED_ENTITY_TYPES:
        raise ValueError(f"Unsupported privacy deletion entity: {entity_type}")
    path = privacy_deletion_ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    record = json.dumps(
        {
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "deleted_at": datetime.now(UTC).isoformat(),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, f"{record}\n".encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def apply_privacy_deletions(db: Session, path: Path | None = None) -> dict[str, int]:
    ledger_path = path or privacy_deletion_ledger_path()
    result = {"records": 0, "clients_deleted": 0, "websites_deleted": 0}
    if not ledger_path.exists():
        return result

    seen: set[tuple[str, UUID]] = set()
    for line_number, line in enumerate(ledger_path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            entity_type = str(record["entity_type"])
            entity_id = UUID(str(record["entity_id"]))
            datetime.fromisoformat(str(record["deleted_at"]))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Invalid privacy deletion ledger record at line {line_number}"
            ) from exc
        if entity_type not in SUPPORTED_ENTITY_TYPES:
            raise ValueError(f"Unsupported privacy deletion entity at line {line_number}")
        seen.add((entity_type, entity_id))

    result["records"] = len(seen)
    for entity_type, entity_id in sorted(
        seen, key=lambda item: (item[0] != "website", str(item[1]))
    ):
        model = Client if entity_type == "client" else Website
        entity = db.get(model, entity_id)
        if entity is None:
            continue
        website_ids = (
            list(db.scalars(select(Website.id).where(Website.client_id == entity_id)))
            if entity_type == "client"
            else [entity_id]
        )
        for sensor_model in SENSOR_WEBSITE_MODELS:
            db.execute(delete(sensor_model).where(sensor_model.website_id.in_(website_ids)))
        if entity_type == "client":
            db.expire(entity, ["websites"])
        db.delete(entity)
        db.flush()
        result[f"{entity_type}s_deleted"] += 1
    db.commit()
    return result

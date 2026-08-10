#!/usr/bin/env python3
import os
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.main import app
from app.models.client import Client
from app.models.discovery import Url
from app.models.sensor import (
    SensorDailyPageMetric,
    SensorManifest,
    SensorMeasurementState,
    SensorOutcomeDefinition,
)
from app.models.website import Website
from app.schemas.sensor import SensorObservation, SensorObservationBatch
from app.services.privacy_deletions import apply_privacy_deletions, record_privacy_deletion

SENSOR_MODELS = (
    SensorManifest,
    SensorOutcomeDefinition,
    SensorDailyPageMetric,
    SensorMeasurementState,
)


def _observation_payload() -> dict[str, object]:
    return {
        "schema_version": "1",
        "client_version": "1.0.0",
        "manifest_version": "2026-08-10.1",
        "event_id": uuid4(),
        "site_key": "public_site_key_1234",
        "session_key": "temporary_session_1234",
        "page_url": "https://sensor-phase-f.example.test/offerte",
        "observed_at": datetime(2026, 8, 10, 12, tzinfo=UTC),
        "name": "process_success",
        "subject": "quote_form",
        "value": {"evidence_strength": "application_event"},
        "trust": "application",
        "priority": "critical",
    }


def _rejects_abuse() -> dict[str, bool]:
    payload = _observation_payload()
    observation = SensorObservation.model_validate(payload)
    checks: dict[str, bool] = {}
    cases = {
        "personal_data": lambda: SensorObservation.model_validate(
            {**payload, "value": {"email": "person@example.test"}}
        ),
        "browser_trust_escalation": lambda: SensorObservation.model_validate(
            {
                **payload,
                "trust": "browser",
                "value": {"evidence_strength": "server_confirmed"},
            }
        ),
        "oversized_batch": lambda: SensorObservationBatch.model_validate(
            {"observations": [{**payload, "event_id": uuid4()} for _ in range(26)]}
        ),
        "replayed_event": lambda: SensorObservationBatch(observations=[observation, observation]),
    }
    for name, case in cases.items():
        try:
            case()
        except ValidationError:
            checks[name] = True
        else:
            checks[name] = False
    assert all(checks.values())
    return checks


def _seed_sensor_data() -> tuple[object, object]:
    with SessionLocal() as db:
        client = Client(name="Release 13 phase F synthetic client")
        website = Website(
            client=client,
            name="Release 13 phase F synthetic site",
            base_url="https://sensor-phase-f.example.test",
        )
        db.add(website)
        db.flush()
        url = Url(
            website_id=website.id,
            normalized_url="https://sensor-phase-f.example.test/offerte",
        )
        db.add(url)
        db.flush()
        db.add_all(
            [
                SensorManifest(
                    website_id=website.id,
                    schema_version="1",
                    manifest_version="2026-08-10.1",
                    profile="lead_generation",
                    page_match="/offerte",
                    observations=[
                        {"key": "quote_form", "kind": "process", "locator": "quote-form"}
                    ],
                    content_hash="a" * 64,
                    status="active",
                    valid_from=datetime(2026, 8, 1, tzinfo=UTC),
                    expires_at=datetime(2026, 9, 1, tzinfo=UTC),
                ),
                SensorOutcomeDefinition(
                    website_id=website.id,
                    key="quote_success",
                    label="Quote success",
                    minimum_evidence="application_event",
                    status="active",
                    valid_from=datetime(2026, 8, 1, tzinfo=UTC),
                ),
                SensorDailyPageMetric(
                    website_id=website.id,
                    url_id=url.id,
                    date=date(2026, 8, 10),
                    manifest_version="2026-08-10.1",
                    page_sessions=10,
                    active_time_buckets={"30_60s": 4},
                    exposures=8,
                    interactions=3,
                    process_starts=2,
                    observed_outcomes=1,
                    trusted_outcomes=0,
                    rejected_count=0,
                    sampled_count=0,
                ),
                SensorMeasurementState(
                    website_id=website.id,
                    period_start=date(2026, 8, 10),
                    period_end=date(2026, 8, 10),
                    status="provisional",
                    client_version="1.0.0",
                    schema_version="1",
                    manifest_version="2026-08-10.1",
                    expected_pages=1,
                    observed_pages=1,
                    rejected_count=0,
                    sampled_count=0,
                    outcome_evidence={"observed": 1, "trusted": 0},
                    checks=[],
                    input_hash="b" * 64,
                ),
            ]
        )
        db.commit()
        return client.id, website.id


def _assert_sensor_data_deleted(website_id: object) -> None:
    with SessionLocal() as db:
        for model in SENSOR_MODELS:
            count = db.scalar(
                select(func.count()).select_from(model).where(model.website_id == website_id)
            )
            assert count == 0


def main() -> None:
    abuse_checks = _rejects_abuse()
    public_paths = app.openapi()["paths"]
    assert not any("sensor" in path or "thactual/observe" in path for path in public_paths)
    client_id, website_id = _seed_sensor_data()
    try:
        with TemporaryDirectory(prefix="release-13-phase-f-") as directory:
            ledger = Path(directory) / "deletions.jsonl"
            previous = os.environ.get("PRIVACY_DELETION_LEDGER_FILE")
            os.environ["PRIVACY_DELETION_LEDGER_FILE"] = str(ledger)
            try:
                record_privacy_deletion("website", website_id)
            finally:
                if previous is None:
                    os.environ.pop("PRIVACY_DELETION_LEDGER_FILE", None)
                else:
                    os.environ["PRIVACY_DELETION_LEDGER_FILE"] = previous
            assert "sensor-phase-f.example.test" not in ledger.read_text()
            with SessionLocal() as db:
                first = apply_privacy_deletions(db, ledger)
                second = apply_privacy_deletions(db, ledger)
            assert first == {"records": 1, "clients_deleted": 0, "websites_deleted": 1}
            assert second == {"records": 1, "clients_deleted": 0, "websites_deleted": 0}

        _assert_sensor_data_deleted(website_id)
    finally:
        with SessionLocal() as db:
            client = db.get(Client, client_id)
            if client is not None:
                db.delete(client)
                db.commit()
    print(
        {
            "status": "release_13_phase_f_staging_ok",
            "public_sensor_routes": 0,
            "abuse_checks": abuse_checks,
            "sensor_tables_deleted": len(SENSOR_MODELS),
            "deletion_replay_idempotent": True,
            "synthetic_data_clean": True,
        }
    )


if __name__ == "__main__":
    main()

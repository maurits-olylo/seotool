from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.discovery import Url
from app.models.sensor import SensorDailyPageMetric, SensorManifest
from app.models.website import Website
from app.services.privacy_deletions import apply_privacy_deletions, record_privacy_deletion


def test_records_minimal_privacy_deletion_without_personal_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with SessionLocal() as db:
        client = Client(name="Privacy client", contact_email="private@example.com")
        db.add(client)
        db.commit()
        ledger = tmp_path / "deletions.jsonl"
        monkeypatch.setenv("PRIVACY_DELETION_LEDGER_FILE", str(ledger))

        record_privacy_deletion("client", client.id)

        record = json.loads(ledger.read_text())
        assert record["entity_type"] == "client"
        assert record["entity_id"] == str(client.id)
        assert "private@example.com" not in ledger.read_text()
        assert ledger.stat().st_mode & 0o777 == 0o600


def test_reapplies_client_and_website_deletions_idempotently(tmp_path: Path) -> None:
    with SessionLocal() as db:
        client = Client(name="Restored client")
        website = Website(client=client, name="Restored website", base_url="https://example.com")
        db.add(client)
        db.commit()
        ledger = tmp_path / "deletions.jsonl"
        ledger.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "entity_type": "website",
                            "entity_id": str(website.id),
                            "deleted_at": "2026-08-06T12:00:00+00:00",
                        }
                    ),
                    json.dumps(
                        {
                            "entity_type": "client",
                            "entity_id": str(client.id),
                            "deleted_at": "2026-08-06T12:01:00+00:00",
                        }
                    ),
                ]
            )
            + "\n"
        )

        first = apply_privacy_deletions(db, ledger)
        second = apply_privacy_deletions(db, ledger)

        assert first == {"records": 2, "clients_deleted": 1, "websites_deleted": 1}
        assert second == {"records": 2, "clients_deleted": 0, "websites_deleted": 0}


def test_rejects_malformed_privacy_deletion_ledger(tmp_path: Path) -> None:
    with SessionLocal() as db:
        ledger = tmp_path / "deletions.jsonl"
        ledger.write_text('{"entity_type":"client"}\n')

        with pytest.raises(ValueError, match="line 1"):
            apply_privacy_deletions(db, ledger)


def test_website_deletion_explicitly_removes_sensor_records(tmp_path: Path) -> None:
    with SessionLocal() as db:
        website = Website(
            client=Client(name="Sensor privacy client"),
            name="Sensor privacy website",
            base_url="https://sensor-privacy.example.test",
        )
        db.add(website)
        db.flush()
        url = Url(website_id=website.id, normalized_url=f"{website.base_url}/offerte")
        db.add(url)
        db.flush()
        db.add_all(
            [
                SensorManifest(
                    website_id=website.id,
                    schema_version="1",
                    manifest_version="v1",
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
                SensorDailyPageMetric(
                    website_id=website.id,
                    url_id=url.id,
                    date=date(2026, 8, 10),
                    manifest_version="v1",
                    page_sessions=1,
                    active_time_buckets={},
                    exposures=0,
                    interactions=0,
                    process_starts=0,
                    observed_outcomes=0,
                    trusted_outcomes=0,
                    rejected_count=0,
                    sampled_count=0,
                ),
            ]
        )
        db.commit()
        ledger = tmp_path / "deletions.jsonl"
        ledger.write_text(
            json.dumps(
                {
                    "entity_type": "website",
                    "entity_id": str(website.id),
                    "deleted_at": "2026-08-10T12:00:00+00:00",
                }
            )
            + "\n"
        )

        apply_privacy_deletions(db, ledger)

        assert db.query(SensorManifest).count() == 0
        assert db.query(SensorDailyPageMetric).count() == 0

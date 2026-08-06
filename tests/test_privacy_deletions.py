from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.client import Client
from app.models.website import Website
from app.services.privacy_deletions import apply_privacy_deletions, record_privacy_deletion


def test_records_minimal_privacy_deletion_without_personal_data(
    db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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


def test_reapplies_client_and_website_deletions_idempotently(db, tmp_path: Path) -> None:
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


def test_rejects_malformed_privacy_deletion_ledger(db, tmp_path: Path) -> None:
    ledger = tmp_path / "deletions.jsonl"
    ledger.write_text('{"entity_type":"client"}\n')

    with pytest.raises(ValueError, match="line 1"):
        apply_privacy_deletions(db, ledger)

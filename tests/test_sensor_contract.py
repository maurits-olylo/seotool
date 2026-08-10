from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.sensor import SensorManifest, SensorObservation, SensorObservationBatch
from app.services.behavioral_provider import BehavioralCapabilities, BehavioralPageAggregate


def _observation(**overrides: object) -> SensorObservation:
    data: dict[str, object] = {
        "schema_version": "1",
        "client_version": "1.0.0",
        "manifest_version": "2026-08-10.1",
        "event_id": uuid4(),
        "site_key": "public_site_key_1234",
        "session_key": "temporary_session_1234",
        "page_url": "https://example.test/offerte",
        "observed_at": datetime(2026, 8, 10, 12, tzinfo=UTC),
        "name": "process_success",
        "subject": "quote_form",
        "value": {"evidence_strength": "application_event"},
        "trust": "application",
        "priority": "critical",
    }
    data.update(overrides)
    return SensorObservation.model_validate(data)


def test_behavioral_contract_exposes_capabilities_without_provider_fields() -> None:
    capabilities = BehavioralCapabilities(page_sessions=True, element_exposure=True)
    aggregate = BehavioralPageAggregate(
        url_id=uuid4(),
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 7),
        page_sessions=20,
        exposures=12,
    )

    assert capabilities.page_sessions is True
    assert capabilities.trusted_outcomes is False
    assert aggregate.exposures == 12
    assert not hasattr(aggregate, "provider")


def test_manifest_requires_stable_unique_allowlisted_observations() -> None:
    manifest = SensorManifest.model_validate(
        {
            "schema_version": "1",
            "manifest_version": "2026-08-10.1",
            "site_key": "public_site_key_1234",
            "profile": "lead_generation",
            "page_match": "/offerte",
            "observations": [
                {"key": "primary_cta", "kind": "exposure", "locator": "primary-cta"},
                {"key": "quote_form", "kind": "process", "locator": "quote-form"},
            ],
            "expires_at": "2026-09-10T00:00:00Z",
        }
    )

    assert len(manifest.observations) == 2

    with pytest.raises(ValidationError, match="observation keys must be unique"):
        SensorManifest.model_validate(
            {
                **manifest.model_dump(),
                "observations": [manifest.observations[0], manifest.observations[0]],
            }
        )


def test_observation_rejects_free_values_and_personal_data_fields() -> None:
    with pytest.raises(ValidationError, match="value keys are not allowed"):
        _observation(value={"email": "person@example.test"})

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _observation(user_id="customer-123")


def test_observation_enforces_subject_and_server_trust() -> None:
    with pytest.raises(ValidationError, match="subject is required"):
        _observation(subject=None)

    trusted = _observation(
        trust="server",
        value={"evidence_strength": "server_confirmed"},
    )
    assert trusted.trust == "server"

    with pytest.raises(ValidationError, match="server_confirmed evidence requires server trust"):
        _observation(value={"evidence_strength": "server_confirmed"})


def test_observation_batch_is_bounded() -> None:
    batch = SensorObservationBatch(observations=[_observation()])
    assert len(batch.observations) == 1

    with pytest.raises(ValidationError):
        SensorObservationBatch(observations=[_observation() for _ in range(26)])

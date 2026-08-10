from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator

ObservationName = Literal[
    "page_view",
    "active_time",
    "element_exposure",
    "element_interaction",
    "process_start",
    "process_success",
    "measurement_status",
]
ObservationPriority = Literal["critical", "important", "optional"]
ObservationTrust = Literal["browser", "application", "server"]
ManifestObservationKind = Literal["exposure", "interaction", "process"]

_SUBJECT_REQUIRED = {
    "element_exposure",
    "element_interaction",
    "process_start",
    "process_success",
}
_VALUE_KEYS: dict[str, set[str]] = {
    "page_view": set(),
    "active_time": {"duration_bucket"},
    "element_exposure": {"visibility_bucket"},
    "element_interaction": {"interaction_type"},
    "process_start": set(),
    "process_success": {"evidence_strength"},
    "measurement_status": {"status"},
}
_VALUE_OPTIONS: dict[str, set[str]] = {
    "duration_bucket": {"0_10s", "10_30s", "30_60s", "60_180s", "180s_plus"},
    "visibility_bucket": {"half_1s", "mostly_1s"},
    "interaction_type": {"click", "submit", "change"},
    "evidence_strength": {
        "click_proxy",
        "thank_you_url",
        "success_state",
        "data_layer",
        "application_event",
        "server_confirmed",
    },
    "status": {"ready", "manifest_missing", "manifest_expired", "consent_blocked", "degraded"},
}


class SensorManifestObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    kind: ManifestObservationKind
    locator: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$")


class SensorManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    manifest_version: str = Field(min_length=1, max_length=40)
    site_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    profile: Literal["lead_generation", "content", "recruitment", "commerce"]
    page_match: str = Field(min_length=1, max_length=512)
    observations: list[SensorManifestObservation] = Field(max_length=20)
    expires_at: datetime

    @field_validator("observations")
    @classmethod
    def observations_have_unique_keys(cls, value: list[SensorManifestObservation]):
        keys = [observation.key for observation in value]
        if len(keys) != len(set(keys)):
            raise ValueError("observation keys must be unique")
        return value


class SensorObservation(BaseModel):
    """Canonical, bounded observation; no arbitrary text or browser-derived identity."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    client_version: str = Field(min_length=1, max_length=32, pattern=r"^[0-9A-Za-z._-]+$")
    manifest_version: str = Field(min_length=1, max_length=40)
    event_id: UUID
    site_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    session_key: str | None = Field(
        default=None,
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    page_url: AnyHttpUrl
    observed_at: datetime
    name: ObservationName
    subject: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    value: dict[str, str] = Field(default_factory=dict, max_length=3)
    trust: ObservationTrust = "browser"
    priority: ObservationPriority

    @model_validator(mode="after")
    def validate_semantics(self):
        if self.name in _SUBJECT_REQUIRED and self.subject is None:
            raise ValueError(f"subject is required for {self.name}")
        if self.name not in _SUBJECT_REQUIRED and self.subject is not None:
            raise ValueError(f"subject is not allowed for {self.name}")

        allowed_keys = _VALUE_KEYS[self.name]
        unexpected = set(self.value) - allowed_keys
        if unexpected:
            raise ValueError(f"value keys are not allowed for {self.name}: {sorted(unexpected)}")
        for key, value in self.value.items():
            if value not in _VALUE_OPTIONS[key]:
                raise ValueError(f"value is not allowed for {key}")

        if self.trust == "server" and self.name != "process_success":
            raise ValueError("server trust is only valid for process_success")
        if self.value.get("evidence_strength") == "server_confirmed" and self.trust != "server":
            raise ValueError("server_confirmed evidence requires server trust")
        if self.trust == "server" and self.value.get("evidence_strength") != "server_confirmed":
            raise ValueError("server trust requires server_confirmed evidence")
        return self


class SensorObservationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observations: Annotated[list[SensorObservation], Field(min_length=1, max_length=25)]

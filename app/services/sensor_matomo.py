from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlencode

from app.schemas.sensor import SensorObservation

MatomoCommandName = Literal["queueRequest",]


@dataclass(frozen=True, slots=True)
class MatomoCommand:
    name: MatomoCommandName
    arguments: tuple[str, ...] = ()


def observation_to_matomo_command(observation: SensorObservation) -> MatomoCommand:
    """Translate canonical semantics at the adapter edge; never expose this to business logic."""

    event_value = (
        observation.subject
        or observation.value.get("duration_bucket")
        or observation.value.get("status")
        or observation.value.get("interaction_type")
        or ("page" if observation.name == "page_view" else None)
        or ""
    )
    return MatomoCommand(
        "queueRequest",
        (
            urlencode(
                {
                    "e_c": "thactual_sensor",
                    "e_a": observation.name,
                    "e_n": f"{observation.manifest_version}:{event_value}",
                }
            ),
        ),
    )

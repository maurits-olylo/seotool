from dataclasses import dataclass
from typing import Literal

from app.schemas.sensor import SensorObservation

MatomoCommandName = Literal[
    "trackPageView",
    "trackEvent",
    "trackContentImpression",
    "trackContentInteraction",
]


@dataclass(frozen=True, slots=True)
class MatomoCommand:
    name: MatomoCommandName
    arguments: tuple[str, ...] = ()


def observation_to_matomo_command(observation: SensorObservation) -> MatomoCommand:
    """Translate canonical semantics at the adapter edge; never expose this to business logic."""

    if observation.name == "page_view":
        return MatomoCommand("trackPageView")
    if observation.name == "element_exposure":
        return MatomoCommand(
            "trackContentImpression",
            (observation.subject or "", observation.manifest_version, observation.page_url.path),
        )
    if observation.name == "element_interaction":
        return MatomoCommand(
            "trackContentInteraction",
            (
                observation.value["interaction_type"],
                observation.subject or "",
                observation.manifest_version,
                observation.page_url.path,
            ),
        )

    event_value = (
        observation.subject
        or observation.value.get("duration_bucket")
        or observation.value.get("status")
        or ""
    )
    return MatomoCommand("trackEvent", ("thactual_sensor", observation.name, event_value))

from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class BehavioralCapabilities:
    """Behavioral evidence a provider can supply without exposing provider semantics."""

    page_sessions: bool = False
    outcomes: bool = False
    entrances: bool = False
    continuation: bool = False
    element_exposure: bool = False
    element_interaction: bool = False
    process_states: bool = False
    active_time: bool = False
    trusted_outcomes: bool = False


@dataclass(frozen=True, slots=True)
class BehavioralPageAggregate:
    url_id: UUID
    period_start: date
    period_end: date
    page_sessions: int | None = None
    entrances: int | None = None
    continuations: int | None = None
    exposures: int | None = None
    interactions: int | None = None
    process_starts: int | None = None
    observed_outcomes: int | None = None
    trusted_outcomes: int | None = None


class BehavioralAggregateProvider(Protocol):
    @property
    def capabilities(self) -> BehavioralCapabilities: ...

    def page_aggregates_between(
        self,
        website_id: UUID,
        period_start: date,
        period_end: date,
    ) -> list[BehavioralPageAggregate]: ...

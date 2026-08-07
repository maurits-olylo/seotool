from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

Device = Literal["desktop", "mobile"]
AiPlatform = Literal["google_ai_overview", "chatgpt", "other"]


def normalized_host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


@dataclass(frozen=True)
class QuestionEvidenceRequest:
    question: str
    language: str
    country: str
    device: Device
    location: str | None = None

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise ValueError("Question must not be empty")
        if len(self.language) != 2 or len(self.country) != 2:
            raise ValueError("Language and country must use two-letter codes")

    @property
    def cache_key(self) -> str:
        normalized_question = " ".join(self.question.lower().split())
        location = (self.location or "").strip().lower()
        return "|".join(
            (
                normalized_question,
                self.language.lower(),
                self.country.upper(),
                self.device,
                location,
            )
        )


@dataclass(frozen=True)
class SourceReference:
    url: str
    title: str | None = None
    position: int | None = None

    @property
    def domain(self) -> str:
        return normalized_host(self.url)


@dataclass(frozen=True)
class SerpObservation:
    provider: str
    observed_at: datetime
    request: QuestionEvidenceRequest
    organic_results: tuple[SourceReference, ...] = ()
    features: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        if len(self.organic_results) > 20:
            raise ValueError("SERP observations are limited to twenty organic results")


@dataclass(frozen=True)
class AiCitationObservation:
    provider: str
    observed_at: datetime
    request: QuestionEvidenceRequest
    platform: AiPlatform
    observed_question: str | None = None
    sources: tuple[SourceReference, ...] = ()
    answer_excerpt: str | None = None
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        if len(self.sources) > 20:
            raise ValueError("AI observations are limited to twenty cited sources")
        if self.answer_excerpt and len(self.answer_excerpt) > 1000:
            raise ValueError("AI answer excerpts are limited to 1000 characters")


@dataclass(frozen=True)
class ProviderUsage:
    provider: str
    cost_micros: int
    units: int = 1
    currency: str = "USD"

    def __post_init__(self) -> None:
        if self.cost_micros < 0 or self.units < 0:
            raise ValueError("Provider usage cannot be negative")


@dataclass(frozen=True)
class ExternalQuestionEvidence:
    request: QuestionEvidenceRequest
    serp: SerpObservation | None = None
    citations: tuple[AiCitationObservation, ...] = ()
    source_coverage: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        observations = ([self.serp] if self.serp else []) + list(self.citations)
        if any(item.request.cache_key != self.request.cache_key for item in observations):
            raise ValueError("All observations must describe the same question context")

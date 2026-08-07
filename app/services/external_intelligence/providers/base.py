from typing import Protocol

from app.services.external_intelligence.contracts import (
    AiCitationObservation,
    QuestionEvidenceRequest,
    SerpObservation,
)


class SerpProvider(Protocol):
    def fetch_serp(self, request: QuestionEvidenceRequest) -> SerpObservation: ...


class AiCitationProvider(Protocol):
    def fetch_citations(
        self, request: QuestionEvidenceRequest
    ) -> tuple[AiCitationObservation, ...]: ...

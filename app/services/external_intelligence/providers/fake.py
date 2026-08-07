from collections.abc import Mapping

from app.services.external_intelligence.contracts import (
    AiCitationObservation,
    QuestionEvidenceRequest,
    SerpObservation,
)


class FakeExternalEvidenceProvider:
    """Deterministic provider for fixtures; it never performs network requests."""

    def __init__(
        self,
        *,
        serp: Mapping[str, SerpObservation] | None = None,
        citations: Mapping[str, tuple[AiCitationObservation, ...]] | None = None,
    ) -> None:
        self._serp = dict(serp or {})
        self._citations = dict(citations or {})
        self.calls: list[tuple[str, str]] = []

    def fetch_serp(self, request: QuestionEvidenceRequest) -> SerpObservation:
        self.calls.append(("serp", request.cache_key))
        try:
            return self._serp[request.cache_key]
        except KeyError as error:
            raise LookupError("No SERP fixture for this request") from error

    def fetch_citations(
        self, request: QuestionEvidenceRequest
    ) -> tuple[AiCitationObservation, ...]:
        self.calls.append(("citations", request.cache_key))
        try:
            return self._citations[request.cache_key]
        except KeyError as error:
            raise LookupError("No citation fixture for this request") from error

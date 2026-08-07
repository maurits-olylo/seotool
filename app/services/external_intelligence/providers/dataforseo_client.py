from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.services.external_intelligence.contracts import (
    AiCitationObservation,
    ProviderUsage,
    QuestionEvidenceRequest,
    SerpObservation,
)
from app.services.external_intelligence.providers.dataforseo import (
    DataForSeoResponseError,
    parse_llm_mentions_response,
    parse_serp_response,
)

BASE_URL = "https://api.dataforseo.com"
SERP_PATH = "/v3/serp/google/organic/live/advanced"
LLM_MENTIONS_PATH = "/v3/ai_optimization/llm_mentions/search_mentions/live"
MAX_RESPONSE_BYTES = 2_000_000


class DataForSeoClient:
    """Bounded paid-provider transport; callers must apply admission policy first."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        if not self.settings.dataforseo_enabled:
            raise ValueError("DataForSEO is not enabled")
        if not self.settings.dataforseo_login or not self.settings.dataforseo_password:
            raise ValueError("DataForSEO credentials are not configured")
        self._http = http

    async def fetch_serp(
        self, request: QuestionEvidenceRequest
    ) -> tuple[SerpObservation, ProviderUsage]:
        payload = await self._post(
            SERP_PATH,
            [
                {
                    "keyword": request.question,
                    **_location(request),
                    "language_code": request.language.lower(),
                    "device": request.device,
                    "depth": 10,
                }
            ],
        )
        return parse_serp_response(payload, request, received_at=datetime.now(UTC))

    async def fetch_citations(
        self, request: QuestionEvidenceRequest
    ) -> tuple[tuple[AiCitationObservation, ...], ProviderUsage]:
        payload = await self._post(
            LLM_MENTIONS_PATH,
            [
                {
                    "target": [
                        {
                            "keyword": request.question,
                            "search_filter": "include",
                            "search_scope": ["question"],
                            "match_type": "word_match",
                        }
                    ],
                    **_location(request),
                    "language_code": request.language.lower(),
                    "platform": "google",
                    "limit": 20,
                }
            ],
        )
        return parse_llm_mentions_response(payload, request, received_at=datetime.now(UTC))

    async def _post(self, path: str, body: list[dict[str, Any]]) -> dict[str, Any]:
        owned_client = self._http is None
        client = self._http or httpx.AsyncClient(base_url=BASE_URL, timeout=130)
        try:
            try:
                response = await client.post(
                    path,
                    json=body,
                    auth=(
                        self.settings.dataforseo_login,
                        self.settings.dataforseo_password,
                    ),
                )
            except httpx.HTTPError as error:
                raise DataForSeoResponseError("DataForSEO request failed") from error
            if response.status_code != 200:
                raise DataForSeoResponseError(
                    f"DataForSEO returned HTTP status {response.status_code}"
                )
            if len(response.content) > MAX_RESPONSE_BYTES:
                raise DataForSeoResponseError("DataForSEO response exceeded the size limit")
            try:
                payload = response.json()
            except ValueError as error:
                raise DataForSeoResponseError("DataForSEO returned invalid JSON") from error
            if not isinstance(payload, dict):
                raise DataForSeoResponseError("DataForSEO returned an invalid response shape")
            return payload
        finally:
            if owned_client:
                await client.aclose()


def _location(request: QuestionEvidenceRequest) -> dict[str, str]:
    if not request.location or not request.location.strip():
        raise ValueError("A verified DataForSEO location name is required")
    return {"location_name": request.location.strip()}

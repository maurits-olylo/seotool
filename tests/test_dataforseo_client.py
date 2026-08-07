import asyncio
import base64
import json
from pathlib import Path

import httpx
import pytest

from app.core.config import Settings
from app.services.external_intelligence.contracts import QuestionEvidenceRequest
from app.services.external_intelligence.providers.dataforseo import DataForSeoResponseError
from app.services.external_intelligence.providers.dataforseo_client import (
    LLM_MENTIONS_PATH,
    SERP_PATH,
    DataForSeoClient,
)

FIXTURES = Path(__file__).parent / "fixtures" / "external_intelligence"


def context(*, location: str | None = "Netherlands") -> QuestionEvidenceRequest:
    return QuestionEvidenceRequest(
        question="wat kosten kunststof kozijnen",
        language="nl",
        country="NL",
        device="mobile",
        location=location,
    )


def settings(*, enabled: bool = True) -> Settings:
    return Settings(
        dataforseo_enabled=enabled,
        dataforseo_login="fixture-login",
        dataforseo_password="fixture-password",
        external_serp_estimated_cost_micros=1,
        external_ai_citations_estimated_cost_micros=1,
    )


def fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text())


def test_serp_transport_uses_bounded_official_request_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == SERP_PATH
        assert request.headers["authorization"] == "Basic " + base64.b64encode(
            b"fixture-login:fixture-password"
        ).decode()
        assert json.loads(request.content) == [
            {
                "keyword": "wat kosten kunststof kozijnen",
                "location_name": "Netherlands",
                "language_code": "nl",
                "device": "mobile",
                "depth": 10,
            }
        ]
        return httpx.Response(
            200,
            json=fixture("dataforseo_serp_live_advanced.json"),
        )

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="https://provider.test"
        ) as http:
            observation, usage = await DataForSeoClient(
                settings=settings(), http=http
            ).fetch_serp(context())
            assert observation.organic_results[0].position == 1
            assert usage.cost_micros == 2000

    asyncio.run(run())


def test_llm_transport_searches_questions_on_google_only() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == LLM_MENTIONS_PATH
        body = json.loads(request.content)[0]
        assert body["platform"] == "google"
        assert body["limit"] == 20
        assert body["target"] == [
            {
                "keyword": "wat kosten kunststof kozijnen",
                "search_filter": "include",
                "search_scope": ["question"],
                "match_type": "word_match",
            }
        ]
        return httpx.Response(
            200,
            json=fixture("dataforseo_llm_mentions_search.json"),
        )

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="https://provider.test"
        ) as http:
            observations, _ = await DataForSeoClient(
                settings=settings(), http=http
            ).fetch_citations(context())
            assert observations[0].platform == "google_ai_overview"

    asyncio.run(run())


def test_client_is_off_by_default_and_requires_explicit_location() -> None:
    with pytest.raises(ValueError, match="not enabled"):
        DataForSeoClient(settings=settings(enabled=False))

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: httpx.Response(500))
        ) as http:
            with pytest.raises(ValueError, match="verified DataForSEO location"):
                await DataForSeoClient(settings=settings(), http=http).fetch_serp(
                    context(location=None)
                )

    asyncio.run(run())


def test_transport_errors_are_sanitized() -> None:
    async def run() -> None:
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(429, text="secret provider response")
        )
        async with httpx.AsyncClient(
            transport=transport, base_url="https://provider.test"
        ) as http:
            with pytest.raises(DataForSeoResponseError, match="HTTP status 429") as error:
                await DataForSeoClient(settings=settings(), http=http).fetch_serp(context())
            assert "secret provider response" not in str(error.value)
            assert "fixture-password" not in str(error.value)

    asyncio.run(run())

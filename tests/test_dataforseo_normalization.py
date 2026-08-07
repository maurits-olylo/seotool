import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.services.external_intelligence.contracts import QuestionEvidenceRequest
from app.services.external_intelligence.providers.dataforseo import (
    DataForSeoResponseError,
    parse_llm_mentions_response,
    parse_serp_response,
)

FIXTURES = Path(__file__).parent / "fixtures" / "external_intelligence"
RECEIVED_AT = datetime(2026, 8, 8, 9, 0, tzinfo=UTC)


def request() -> QuestionEvidenceRequest:
    return QuestionEvidenceRequest(
        question="wat kosten kunststof kozijnen",
        language="nl",
        country="NL",
        device="mobile",
        location="Nederland",
    )


def fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text())


def test_maps_serp_organic_results_features_timestamp_and_usage() -> None:
    observation, usage = parse_serp_response(
        fixture("dataforseo_serp_live_advanced.json"),
        request(),
        received_at=RECEIVED_AT,
    )

    assert [item.url for item in observation.organic_results] == [
        "https://voorbeeld.nl/kosten",
        "https://ander.nl/prijzen",
    ]
    assert observation.organic_results[0].position == 1
    assert observation.features == ("ai_overview", "people_also_ask")
    assert observation.observed_at == datetime(2026, 8, 8, 8, 30, tzinfo=UTC)
    assert usage.cost_micros == 2000
    assert not hasattr(observation, "task_id")


def test_maps_only_actual_citation_sources_and_preserves_observed_question() -> None:
    observations, usage = parse_llm_mentions_response(
        fixture("dataforseo_llm_mentions_search.json"),
        request(),
        received_at=RECEIVED_AT,
    )

    observation = observations[0]
    assert observation.platform == "google_ai_overview"
    assert observation.observed_question == "Wat kosten kunststof kozijnen gemiddeld?"
    assert [source.url for source in observation.sources] == ["https://bron.nl/kozijnen"]
    assert all(source.domain != "eigen-site.nl" for source in observation.sources)
    assert usage.cost_micros == 10100


def test_truncates_answer_and_uses_received_at_for_invalid_timestamp() -> None:
    payload = fixture("dataforseo_llm_mentions_search.json")
    result = payload["tasks"][0]["result"][0]  # type: ignore[index]
    result["answer"] = "x" * 1001
    result["last_response_at"] = "invalid"

    observations, _ = parse_llm_mentions_response(
        payload, request(), received_at=RECEIVED_AT
    )

    assert observations[0].observed_at == RECEIVED_AT
    assert len(observations[0].answer_excerpt or "") == 1000
    assert "provider_timestamp_missing_or_invalid" in observations[0].warnings


def test_rejects_failed_task_without_exposing_raw_payload() -> None:
    payload = {
        "tasks": [
            {
                "status_code": 40501,
                "status_message": "Invalid field",
                "secret": "must-not-leak",
            }
        ]
    }

    with pytest.raises(DataForSeoResponseError, match="40501: Invalid field") as error:
        parse_serp_response(payload, request(), received_at=RECEIVED_AT)

    assert "must-not-leak" not in str(error.value)

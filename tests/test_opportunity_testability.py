from app.services.opportunity_testability import (
    detect_underperforming_winners,
    device_friction_candidate,
    intent_mismatch_candidates,
    journey_friction_candidates,
)
from app.services.opportunity_testability import (
    testability_band as classify_testability,
)


def test_testability_bands_remain_advisory() -> None:
    assert classify_testability(volume=500, outcome_events=20, outcome_available=True) == "testable"
    assert (
        classify_testability(volume=150, outcome_events=0, outcome_available=True)
        == "longer_observation_needed"
    )
    assert (
        classify_testability(volume=500, outcome_events=20, outcome_available=False)
        == "effect_measurement_preferred"
    )


def test_underperforming_winner_requires_search_role_and_outcome_context() -> None:
    pages = [
        {
            "url_id": "winner",
            "content_role": "convert",
            "visits": 200,
            "conversions": 0,
        },
        {
            "url_id": "peer",
            "content_role": "convert",
            "visits": 800,
            "conversions": 20,
        },
    ]

    result = detect_underperforming_winners(pages, {"winner": 500, "peer": 100})

    assert [item.url_id for item in result] == ["winner"]
    assert result[0].pattern == "underperforming_winner"
    assert result[0].evidence["interpretation"] == "geobserveerde samenhang; geen causaliteitsclaim"
    assert detect_underperforming_winners(pages, {"winner": 249}) == []


def test_journey_friction_is_presented_as_candidate_not_proven_problem() -> None:
    result = journey_friction_candidates(
        [
            {
                "url_id": "page",
                "entry_visits": 120,
                "continuations": 5,
                "continuation_rate": 0.0417,
                "benchmark_rate": 0.3,
                "confidence": 0.95,
            }
        ]
    )

    assert result[0].pattern == "journey_friction"
    assert result[0].evidence["interpretation"] == "testkandidaat; probleem niet bewezen"


def test_intent_mismatch_requires_commercial_demand_on_informational_page() -> None:
    insight = {
        "url_id": "page",
        "query": "wat kost isolatie",
        "intent": "prijs",
        "impressions": 300,
        "clicks": 12,
        "coverage_status": "partial",
    }

    result = intent_mismatch_candidates([insight], {"page": "informational"})

    assert result[0].pattern == "intent_mismatch"
    assert "geen bewezen mismatch" in result[0].evidence["interpretation"]
    assert intent_mismatch_candidates([insight], {"page": "transactional"}) == []


def test_device_friction_requires_explicit_mobile_volume() -> None:
    assert (
        device_friction_candidate(
            url_id="page", mobile_volume=None, mobile_score=0.4, desktop_score=0.8
        )
        is None
    )
    candidate = device_friction_candidate(
        url_id="page", mobile_volume=200, mobile_score=0.4, desktop_score=0.8
    )
    assert candidate is not None
    assert candidate.pattern == "device_friction"

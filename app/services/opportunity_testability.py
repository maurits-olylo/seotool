from dataclasses import dataclass

COMMERCIAL_ROLES = {"convert", "support_choice"}
PILOT_METHOD_VERSION = "testability-pilot-2026-08-v1"


@dataclass(frozen=True)
class TestingCandidate:
    pattern: str
    url_id: str
    volume: int
    outcome_events: float
    evidence: dict[str, object]


def testability_band(*, volume: int, outcome_events: float, outcome_available: bool) -> str:
    """Return a provisional pilot band, never a statistical or causal claim."""
    if outcome_available and volume >= 300 and outcome_events >= 10:
        return "testable"
    if outcome_available and volume >= 100:
        return "longer_observation_needed"
    return "effect_measurement_preferred"


def detect_underperforming_winners(
    pages: list[dict[str, object]], search_impressions: dict[str, int]
) -> list[TestingCandidate]:
    total_visits = sum(int(page.get("visits") or 0) for page in pages)
    total_conversions = sum(float(page.get("conversions") or 0) for page in pages)
    site_rate = total_conversions / total_visits if total_visits else 0
    if total_visits < 500 or site_rate < 0.005:
        return []
    candidates: list[TestingCandidate] = []
    for page in pages:
        url_id = str(page.get("url_id") or "")
        visits = int(page.get("visits") or 0)
        conversions = float(page.get("conversions") or 0)
        impressions = int(search_impressions.get(url_id, 0))
        rate = conversions / visits if visits else 0
        expected = visits * site_rate
        if (
            page.get("content_role") not in COMMERCIAL_ROLES
            or visits < 150
            or impressions < 250
            or expected < 3
            or rate > site_rate * 0.4
        ):
            continue
        candidates.append(
            TestingCandidate(
                pattern="underperforming_winner",
                url_id=url_id,
                volume=max(visits, impressions),
                outcome_events=conversions,
                evidence={
                    "visits": visits,
                    "search_impressions": impressions,
                    "conversions": round(conversions, 1),
                    "conversion_rate": round(rate, 4),
                    "site_conversion_rate": round(site_rate, 4),
                    "interpretation": "geobserveerde samenhang; geen causaliteitsclaim",
                },
            )
        )
    return sorted(candidates, key=lambda item: item.volume, reverse=True)[:5]


def journey_friction_candidates(
    opportunities: list[dict[str, object]],
) -> list[TestingCandidate]:
    return [
        TestingCandidate(
            pattern="journey_friction",
            url_id=str(item["url_id"]),
            volume=int(item.get("entry_visits") or 0),
            outcome_events=float(item.get("continuations") or 0),
            evidence={
                "entry_visits": int(item.get("entry_visits") or 0),
                "continuation_rate": item.get("continuation_rate"),
                "benchmark_rate": item.get("benchmark_rate"),
                "confidence": item.get("confidence"),
                "interpretation": "testkandidaat; probleem niet bewezen",
            },
        )
        for item in opportunities
    ]


def intent_mismatch_candidates(
    insights: list[dict[str, object]],
    page_intents: dict[str, str],
) -> list[TestingCandidate]:
    commercial_intents = {"prijs", "vergelijking", "geschiktheid"}
    candidates = []
    for item in insights:
        url_id = str(item.get("url_id") or "")
        impressions = int(item.get("impressions") or 0)
        if (
            item.get("intent") not in commercial_intents
            or page_intents.get(url_id) != "informational"
            or impressions < 150
        ):
            continue
        candidates.append(
            TestingCandidate(
                pattern="intent_mismatch",
                url_id=url_id,
                volume=impressions,
                outcome_events=float(item.get("clicks") or 0),
                evidence={
                    "query": item.get("query"),
                    "query_intent": item.get("intent"),
                    "page_intent": "informational",
                    "impressions": impressions,
                    "coverage_status": item.get("coverage_status"),
                    "interpretation": (
                        "hypothese op basis van vraag en pagina; geen bewezen mismatch"
                    ),
                },
            )
        )
    return sorted(candidates, key=lambda item: item.volume, reverse=True)[:5]


def device_friction_candidate(
    *,
    url_id: str,
    mobile_volume: int | None,
    mobile_score: float | None,
    desktop_score: float | None,
) -> TestingCandidate | None:
    """Require explicit device-segmented volume before suggesting a mobile test."""
    if (
        mobile_volume is None
        or mobile_volume < 150
        or mobile_score is None
        or desktop_score is None
        or mobile_score > 0.6
        or desktop_score - mobile_score < 0.2
    ):
        return None
    return TestingCandidate(
        pattern="device_friction",
        url_id=url_id,
        volume=mobile_volume,
        outcome_events=0,
        evidence={
            "mobile_volume": mobile_volume,
            "mobile_performance": mobile_score,
            "desktop_performance": desktop_score,
            "interpretation": "apparaatverschil; effect van een wijziging nog te meten",
        },
    )

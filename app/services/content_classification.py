from collections.abc import Mapping

SEARCH_INTENTS = frozenset(
    {"informational", "commercial", "transactional", "trust", "navigational", "mixed", "uncertain"}
)
JOURNEY_STAGES = frozenset(
    {"discover", "understand", "consider", "compare", "decide", "act", "aftercare", "uncertain"}
)
CONTENT_ROLES = frozenset(
    {
        "attract",
        "support_choice",
        "provide_proof",
        "convert",
        "navigate",
        "support_customers",
        "uncertain",
    }
)


def validate_label(value: str | None, allowed: frozenset[str], field_name: str) -> None:
    if value is not None and value not in allowed:
        raise ValueError(f"Invalid {field_name}: {value}")


def validate_probabilities(probabilities: Mapping[str, float]) -> dict[str, float]:
    if not probabilities:
        raise ValueError("Probabilities must not be empty")
    normalized = {str(label): float(value) for label, value in probabilities.items()}
    if any(value < 0 or value > 1 for value in normalized.values()):
        raise ValueError("Probabilities must be between zero and one")
    if abs(sum(normalized.values()) - 1.0) > 0.001:
        raise ValueError("Probabilities must add up to one")
    return normalized


def normalize_branded_terms(terms: list[str]) -> list[str]:
    normalized = {" ".join(term.lower().split()) for term in terms if term.strip()}
    return sorted(normalized)

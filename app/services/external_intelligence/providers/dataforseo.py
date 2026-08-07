from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.services.external_intelligence.contracts import (
    AiCitationObservation,
    AiPlatform,
    ProviderUsage,
    QuestionEvidenceRequest,
    SerpObservation,
    SourceReference,
)

PROVIDER = "dataforseo"
SUCCESS_STATUS = 20000
MAX_RESULTS = 20


class DataForSeoResponseError(ValueError):
    """A sanitized provider response error without raw payload data."""


def parse_serp_response(
    payload: Mapping[str, Any],
    request: QuestionEvidenceRequest,
    *,
    received_at: datetime,
) -> tuple[SerpObservation, ProviderUsage]:
    task = _successful_task(payload)
    result = _first_mapping(task.get("result"))
    warnings: list[str] = []
    organic_results: list[SourceReference] = []
    features: list[str] = []

    for item in _mapping_items(result.get("items")):
        item_type = _text(item.get("type"))
        if item_type == "organic":
            url = _text(item.get("url"))
            if not url:
                warnings.append("organic_result_without_url")
                continue
            if len(organic_results) < MAX_RESULTS:
                organic_results.append(
                    SourceReference(
                        url=url,
                        title=_optional_text(item.get("title")),
                        position=_positive_int(item.get("rank_group")),
                    )
                )
            elif "organic_results_truncated" not in warnings:
                warnings.append("organic_results_truncated")
        elif item_type and item_type not in features:
            features.append(item_type)

    if not organic_results:
        warnings.append("no_organic_results")

    observed_at = _timestamp(result.get("datetime"), received_at, warnings)
    return (
        SerpObservation(
            provider=PROVIDER,
            observed_at=observed_at,
            request=request,
            organic_results=tuple(organic_results),
            features=tuple(features[:MAX_RESULTS]),
            warnings=tuple(warnings),
        ),
        _usage(payload, task),
    )


def parse_llm_mentions_response(
    payload: Mapping[str, Any],
    request: QuestionEvidenceRequest,
    *,
    received_at: datetime,
) -> tuple[tuple[AiCitationObservation, ...], ProviderUsage]:
    task = _successful_task(payload)
    warnings: list[str] = []
    observations: list[AiCitationObservation] = []

    for result in _mapping_items(task.get("result")):
        if len(observations) >= MAX_RESULTS:
            warnings.append("citation_observations_truncated")
            break
        item_warnings: list[str] = []
        sources: list[SourceReference] = []
        for source in _mapping_items(result.get("sources")):
            url = _text(source.get("url"))
            if not url:
                item_warnings.append("citation_source_without_url")
                continue
            if len(sources) < MAX_RESULTS:
                sources.append(
                    SourceReference(
                        url=url,
                        title=_optional_text(source.get("title")),
                        position=_positive_int(source.get("rank")),
                    )
                )
            elif "citation_sources_truncated" not in item_warnings:
                item_warnings.append("citation_sources_truncated")
        if not sources:
            item_warnings.append("no_cited_sources")

        answer = _optional_text(result.get("answer"))
        observed_at = _timestamp(result.get("last_response_at"), received_at, item_warnings)
        observations.append(
            AiCitationObservation(
                provider=PROVIDER,
                observed_at=observed_at,
                request=request,
                platform=_platform(result),
                observed_question=_optional_text(result.get("question")),
                sources=tuple(sources),
                answer_excerpt=answer[:1000] if answer else None,
                warnings=tuple(item_warnings),
            )
        )

    if not observations:
        warnings.append("no_ai_observations")
    if warnings and observations:
        first = observations[0]
        observations[0] = AiCitationObservation(
            provider=first.provider,
            observed_at=first.observed_at,
            request=first.request,
            platform=first.platform,
            observed_question=first.observed_question,
            sources=first.sources,
            answer_excerpt=first.answer_excerpt,
            warnings=first.warnings + tuple(warnings),
        )
    return tuple(observations), _usage(payload, task)


def _successful_task(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    task = _first_mapping(payload.get("tasks"))
    status_code = task.get("status_code")
    if status_code != SUCCESS_STATUS:
        message = _text(task.get("status_message")) or "unknown provider error"
        raise DataForSeoResponseError(f"DataForSEO task {status_code}: {message}")
    return task


def _usage(payload: Mapping[str, Any], task: Mapping[str, Any]) -> ProviderUsage:
    raw_cost = task.get("cost", payload.get("cost", 0))
    try:
        cost_micros = int(
            (Decimal(str(raw_cost)) * Decimal(1_000_000)).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
    except (InvalidOperation, TypeError, ValueError) as error:
        raise DataForSeoResponseError("DataForSEO returned an invalid cost") from error
    return ProviderUsage(provider=PROVIDER, cost_micros=cost_micros)


def _timestamp(value: object, fallback: datetime, warnings: list[str]) -> datetime:
    if fallback.tzinfo is None:
        raise ValueError("received_at must be timezone-aware")
    text = _optional_text(value)
    if text:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed
        except ValueError:
            pass
    warnings.append("provider_timestamp_missing_or_invalid")
    return fallback.astimezone(UTC)


def _platform(result: Mapping[str, Any]) -> AiPlatform:
    platform = _text(result.get("platform"))
    model_name = _text(result.get("model_name"))
    if platform == "google" or model_name == "google_ai_overview":
        return "google_ai_overview"
    if platform == "chat_gpt":
        return "chatgpt"
    return "other"


def _first_mapping(value: object) -> Mapping[str, Any]:
    items = _mapping_items(value)
    if not items:
        raise DataForSeoResponseError("DataForSEO response contains no task result")
    return items[0]


def _mapping_items(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _optional_text(value: object) -> str | None:
    return _text(value) or None


def _positive_int(value: object) -> int | None:
    return value if isinstance(value, int) and value > 0 else None

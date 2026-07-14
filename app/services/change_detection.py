import json
from dataclasses import dataclass

from app.models.crawl import UrlSnapshot


@dataclass(frozen=True)
class DetectedChange:
    change_type: str
    field_name: str
    old_value: str | None
    new_value: str | None


FIELDS = {
    "status_code": "status_code_changed",
    "final_url": "redirect_target_changed",
    "title": "title_changed",
    "meta_description": "description_changed",
    "canonical": "canonical_changed",
    "meta_robots": "robots_changed",
    "x_robots_tag": "robots_changed",
    "is_indexable": "indexability_changed",
    "main_content_hash": "main_content_changed",
}
NORMALIZED_TEXT_FIELDS = {"title", "meta_description", "meta_robots", "x_robots_tag"}


def compare_snapshots(previous: UrlSnapshot | None, current: UrlSnapshot) -> list[DetectedChange]:
    if previous is None:
        return [DetectedChange("new_url", "url", None, current.requested_url)]
    changes: list[DetectedChange] = []
    for field, change_type in FIELDS.items():
        old = getattr(previous, field)
        new = getattr(current, field)
        if not _values_equal(field, old, new):
            changes.append(DetectedChange(change_type, field, _serialize(old), _serialize(new)))
    old_h1 = _normalized_text_list((previous.headings or {}).get("h1", []))
    new_h1 = _normalized_text_list((current.headings or {}).get("h1", []))
    if old_h1 != new_h1:
        changes.append(
            DetectedChange("h1_changed", "headings.h1", _serialize(old_h1), _serialize(new_h1))
        )
    old_schema = _canonical_schema(previous.schema_data or [])
    new_schema = _canonical_schema(current.schema_data or [])
    if old_schema != new_schema:
        changes.append(
            DetectedChange(
                "structured_data_changed",
                "schema_data",
                _serialize(old_schema),
                _serialize(new_schema),
            )
        )
    return changes


def _values_equal(field: str, old: object, new: object) -> bool:
    if field in NORMALIZED_TEXT_FIELDS and isinstance(old, str) and isinstance(new, str):
        return " ".join(old.split()) == " ".join(new.split())
    return old == new


def _canonical_schema(value: list[object]) -> list[object]:
    canonical = [_canonical_schema_value(item) for item in value]
    return sorted(
        canonical,
        key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False),
    )


def _canonical_schema_value(value: object, *, unordered: bool = False) -> object:
    if isinstance(value, dict):
        return {
            key: _canonical_schema_value(
                child,
                unordered=key in {"@graph", "@type"},
            )
            for key, child in value.items()
        }
    if isinstance(value, list):
        children = [_canonical_schema_value(child) for child in value]
        if unordered:
            return sorted(
                children,
                key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False),
            )
        return children
    return value


def _normalized_text_list(values: list[object]) -> list[object]:
    return [" ".join(value.split()) if isinstance(value, str) else value for value in values]


def _serialize(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)

"""Presentation-only grouping; never merge stored issues or tasks."""

from typing import Any


def group_duplicates(items: list[dict], evidence: dict, details: dict) -> list[dict]:
    groups: dict[tuple, list[dict]] = {}
    result = []
    for item in items:
        occurrence = evidence.get(item["issue_id"])
        payload = details.get(occurrence.id, {}) if occurrence else {}
        related = payload.get("related_urls")
        value = payload.get("value")
        if (
            item["issue_type"] not in {"duplicate_title", "duplicate_meta_description"}
            or not item.get("url")
            or not isinstance(value, str)
            or not value
            or not isinstance(related, list)
            or not related
            or not all(isinstance(url, str) for url in related)
        ):
            result.append(item)
            continue
        key = (
            item["issue_type"],
            occurrence.crawl_run_id,
            value,
            tuple(sorted(set([item["url"], *related]))),
            item["lane"],
            item["status"],
            item["severity"],
            item["evidence_code"],
            item["reason"],
            item["first_step"],
            item["completion"],
        )
        groups.setdefault(key, []).append(item)
    for key, members in groups.items():
        # All group members must independently agree. Missing/changed members
        # mean separate cards, even when the older evidence names the same group.
        if len(members) < 2 or {m["url"] for m in members} != set(key[3]):
            result.extend(members)
            continue
        members.sort(key=lambda m: (m["url"], str(m["issue_id"])))
        grouped: dict[str, Any] = dict(members[0])
        grouped["members"] = members
        grouped["tasks"] = list({str(t["id"]): t for m in members for t in m["tasks"]}.values())
        result.append(grouped)
    return result

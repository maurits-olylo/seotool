from datetime import UTC, date, datetime
from typing import Any

from app.services.technical_checks import IssueSignal


def inspect_job_posting(
    schema_data: list[object], *, today: date | None = None, status_code: int | None = 200
) -> list[IssueSignal]:
    today = today or datetime.now(UTC).date()
    jobs = list(_find_job_postings(schema_data))
    signals: list[IssueSignal] = []
    for job in jobs:
        valid_through = _parse_date(job.get("validThrough"))
        if valid_through and valid_through < today and status_code == 200:
            signals.append(
                IssueSignal(
                    "expired_job_posting",
                    "content",
                    "high",
                    "Vacature is verlopen maar nog online",
                    f"validThrough ({valid_through.isoformat()}) ligt in het verleden.",
                    "Sluit of actualiseer de vacature en wijzig het JobPosting-schema.",
                    {"validThrough": valid_through.isoformat()},
                )
            )
        missing = [field for field in ("title", "description", "datePosted") if not job.get(field)]
        if missing:
            signals.append(
                IssueSignal(
                    "job_posting_missing_fields",
                    "structured_data",
                    "medium",
                    "JobPosting mist verplichte velden",
                    f"Ontbrekende velden: {', '.join(missing)}.",
                    "Vul de ontbrekende JobPosting-velden aan.",
                    {"missing_fields": missing},
                )
            )
    return signals


def _find_job_postings(value: object):  # type: ignore[no-untyped-def]
    if isinstance(value, dict):
        schema_type = value.get("@type")
        types = [schema_type] if isinstance(schema_type, str) else schema_type or []
        if "JobPosting" in types:
            yield value
        for child in value.values():
            yield from _find_job_postings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _find_job_postings(child)


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None

from datetime import UTC, date, datetime
import re
from typing import Any
from urllib.parse import urlsplit

from app.services.technical_checks import IssueSignal

APPLICATION_CTA_RE = re.compile(r"\b(solliciteer|reageer|aanmelden|apply)\b", re.IGNORECASE)
JOB_URL_RE = re.compile(r"/(vacature|vacatures|werken-bij|jobs?|carriere)(/|$)", re.IGNORECASE)
CLOSING_DATE_RE = re.compile(
    r"(?:solliciteren\s+tot|reageer\s+(?:voor|v[oó]or)|sluitingsdatum|deadline)\s*(?:is|:)?\s*"
    r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{1,2}\s+"
    r"(?:januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december)\s+\d{4})",
    re.IGNORECASE,
)
MONTHS_NL = {
    "januari": 1, "februari": 2, "maart": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "augustus": 8, "september": 9, "oktober": 10, "november": 11,
    "december": 12,
}


def inspect_job_posting(
    schema_data: list[object],
    *,
    today: date | None = None,
    status_code: int | None = 200,
    page_url: str | None = None,
    main_content: str | None = None,
    has_application_cta: bool = False,
    inbound_internal_links: int = 0,
    was_job_posting: bool = False,
) -> list[IssueSignal]:
    today = today or datetime.now(UTC).date()
    jobs = list(_find_job_postings(schema_data))
    signals: list[IssueSignal] = []
    is_job_url = bool(page_url and JOB_URL_RE.search(urlsplit(page_url).path))
    if status_code in {404, 410} and (jobs or was_job_posting or is_job_url):
        return [
            IssueSignal(
                "expired_job_posting_404",
                "content",
                "high",
                "Vacature is niet meer bereikbaar",
                "De vacature-URL geeft een fout zonder actuele vacaturepagina.",
                "Stel een relevante redirect in of verwijder resterende verwijzingen naar de vacature.",
                {"status_code": status_code, "was_job_posting": was_job_posting},
            )
        ]

    expiration_evidence: dict[str, object] = {}
    for job in jobs:
        valid_through = _parse_date(job.get("validThrough"))
        if valid_through and valid_through < today and status_code == 200:
            expiration_evidence["validThrough"] = valid_through.isoformat()
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

    visible_deadline = _visible_expired_deadline(main_content or "", today)
    if visible_deadline and has_application_cta:
        expiration_evidence["visible_closing_date"] = visible_deadline.isoformat()
        expiration_evidence["application_cta_active"] = True
    if expiration_evidence:
        signals.append(
            IssueSignal(
                "expired_job_posting",
                "content",
                "high",
                "Vacature is verlopen maar nog online",
                _expiration_description(expiration_evidence),
                "Sluit of actualiseer de vacature, verwijder de sollicitatie-CTA en werk het JobPosting-schema bij.",
                expiration_evidence,
            )
        )
        if inbound_internal_links:
            signals.append(
                IssueSignal(
                    "expired_job_posting_linked",
                    "internal_links",
                    "medium",
                    "Verlopen vacature heeft interne links",
                    f"De verlopen vacature heeft nog {inbound_internal_links} interne verwijzingen.",
                    "Verwijder of vervang interne links naar deze verlopen vacature.",
                    {"inbound_internal_links": inbound_internal_links},
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


def _visible_expired_deadline(content: str, today: date) -> date | None:
    match = CLOSING_DATE_RE.search(content)
    if not match:
        return None
    value = match.group(1).lower()
    try:
        if " " not in value:
            day, month, year = re.split(r"[-/]", value)
            parsed_year = int(year) + 2000 if len(year) == 2 else int(year)
            parsed = date(parsed_year, int(month), int(day))
        else:
            day, month_name, year = value.split()
            parsed = date(int(year), MONTHS_NL[month_name], int(day))
    except (KeyError, ValueError):
        return None
    return parsed if parsed < today else None


def _expiration_description(evidence: dict[str, object]) -> str:
    details: list[str] = []
    if "validThrough" in evidence:
        details.append(f"validThrough ({evidence['validThrough']}) ligt in het verleden")
    if "visible_closing_date" in evidence:
        details.append(f"zichtbare sluitingsdatum ({evidence['visible_closing_date']}) ligt in het verleden")
    if evidence.get("application_cta_active"):
        details.append("de sollicitatie-CTA is nog actief")
    return "; ".join(details) + "."

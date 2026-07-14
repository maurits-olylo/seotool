import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from app.services.technical_checks import IssueSignal

APPLICATION_CTA_RE = re.compile(r"\b(solliciteer|reageer|aanmelden|apply)\b", re.IGNORECASE)
JOB_URL_RE = re.compile(r"/(vacature|vacatures|werken-bij|jobs?|carriere)(/|$)", re.IGNORECASE)
JOB_DETAIL_URL_RE = re.compile(r"/(?:vacatures?|werken-bij|jobs?|carriere)/.+", re.IGNORECASE)
JOB_TERMS_RE = re.compile(
    r"\b(vacature|functie|solliciteer|werken bij|job opening|jobomschrijving)\b", re.IGNORECASE
)
CLOSING_DATE_RE = re.compile(
    r"(?:solliciteren\s+tot|reageer\s+(?:voor|v[oó]or)|sluitingsdatum|deadline)\s*(?:is|:)?\s*"
    r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{1,2}\s+"
    r"(?:januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december)\s+\d{4})",
    re.IGNORECASE,
)
MONTHS_NL = {
    "januari": 1,
    "februari": 2,
    "maart": 3,
    "april": 4,
    "mei": 5,
    "juni": 6,
    "juli": 7,
    "augustus": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "december": 12,
}

ACTIVE_JOB_ISSUE_STATUSES = {
    "new",
    "review",
    "accepted",
    "planned",
    "in_progress",
    "waiting_for_client",
}
JOB_ISSUE_TYPES = {
    "expired_job_posting",
    "expired_job_posting_linked",
    "expired_job_posting_404",
    "job_posting_schema_missing",
    "job_posting_missing_fields",
    "job_posting_invalid_dates",
    "job_posting_missing_application",
    "job_posting_remote_location_missing",
    "job_posting_location_incomplete",
    "job_posting_not_detail_page",
    "job_posting_missing_recommended_fields",
}


@dataclass(frozen=True)
class RecognizedJobListing:
    detection_sources: list[str]
    title: str | None
    employer: str | None
    locations: list[str]
    date_posted: date | None
    valid_through: date | None
    salary_data: dict[str, object]
    hours: str | None
    employment_types: list[str]
    external_identifier: str | None
    application_url: str | None
    job_posting_data: dict[str, object]
    lifecycle_status: str


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
                (
                    "Stel een relevante redirect in of verwijder resterende verwijzingen "
                    "naar de vacature."
                ),
                {"status_code": status_code, "was_job_posting": was_job_posting},
            )
        ]

    if not jobs and _looks_like_job_detail_page(page_url, main_content or ""):
        signals.append(
            IssueSignal(
                "job_posting_schema_missing",
                "structured_data",
                "high",
                "Vacature mist JobPosting-schema",
                (
                    "Deze individuele vacaturepagina is herkend aan URL en inhoud, maar bevat "
                    "geen JobPosting-schema."
                ),
                (
                    "Voeg volledig JobPosting-schema toe met onder meer titel, omschrijving, "
                    "werkgever, datum en vacaturelocatie."
                ),
                {"source": "url_and_page_text", "page_url": page_url},
                confidence="medium",
            )
        )

    expiration_evidence: dict[str, object] = {}
    for job in jobs:
        signals.extend(
            _google_for_jobs_signals(
                job,
                page_url=page_url,
                main_content=main_content or "",
                has_application_cta=has_application_cta,
            )
        )
        valid_through = _parse_date(job.get("validThrough"))
        if valid_through and valid_through < today and status_code == 200:
            expiration_evidence["validThrough"] = valid_through.isoformat()

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
                (
                    "Sluit of actualiseer de vacature, verwijder de sollicitatie-CTA en werk "
                    "het JobPosting-schema bij."
                ),
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
                    (
                        f"De verlopen vacature heeft nog {inbound_internal_links} "
                        "interne verwijzingen."
                    ),
                    "Verwijder of vervang interne links naar deze verlopen vacature.",
                    {"inbound_internal_links": inbound_internal_links},
                )
            )
    return signals


def _google_for_jobs_signals(
    job: dict[str, object],
    *,
    page_url: str | None,
    main_content: str,
    has_application_cta: bool,
) -> list[IssueSignal]:
    """Validate the JobPosting properties that Google needs for job listings."""
    signals: list[IssueSignal] = []
    missing = _missing_required_job_fields(job)
    if missing:
        signals.append(
            IssueSignal(
                "job_posting_missing_fields",
                "structured_data",
                "high",
                "JobPosting mist verplichte velden",
                f"Ontbrekende of ongeldige velden: {', '.join(missing)}.",
                "Vul de ontbrekende JobPosting-velden aan op deze individuele vacaturepagina.",
                {"missing_fields": missing, "source": "google_for_jobs"},
            )
        )

    invalid_dates = _invalid_job_dates(job)
    if invalid_dates:
        signals.append(
            IssueSignal(
                "job_posting_invalid_dates",
                "structured_data",
                "high",
                "JobPosting bevat ongeldige datums",
                f"Controleer: {', '.join(invalid_dates)}.",
                "Gebruik geldige ISO-datums en zorg dat validThrough niet vóór datePosted ligt.",
                {"invalid_dates": invalid_dates, "source": "google_for_jobs"},
            )
        )

    if not has_application_cta and not APPLICATION_CTA_RE.search(main_content):
        signals.append(
            IssueSignal(
                "job_posting_missing_application",
                "content",
                "high",
                "Vacature heeft geen herkenbare sollicitatiemogelijkheid",
                (
                    "Op de vacaturepagina is geen herkenbare sollicitatie-CTA of "
                    "sollicitatielink gevonden."
                ),
                "Voeg een direct bereikbare sollicitatiemogelijkheid toe aan de vacaturepagina.",
                {"source": "google_for_jobs"},
                confidence="medium",
            )
        )

    if _is_remote_job(job) and not job.get("applicantLocationRequirements"):
        signals.append(
            IssueSignal(
                "job_posting_remote_location_missing",
                "structured_data",
                "high",
                "Remote vacature mist toegestane werklocatie",
                "jobLocationType is TELECOMMUTE, maar applicantLocationRequirements ontbreekt.",
                "Vermeld voor remote werk waar kandidaten zich moeten bevinden.",
                {"source": "google_for_jobs"},
            )
        )
    elif job.get("jobLocation") and _job_location_missing_country(job.get("jobLocation")):
        signals.append(
            IssueSignal(
                "job_posting_location_incomplete",
                "structured_data",
                "medium",
                "Vacaturelocatie mist land",
                "Een JobPosting met jobLocation bevat geen addressCountry.",
                "Vul addressCountry aan bij iedere fysieke vacaturelocatie.",
                {"source": "google_for_jobs"},
            )
        )

    if (
        page_url
        and JOB_URL_RE.search(urlsplit(page_url).path)
        and not JOB_DETAIL_URL_RE.search(urlsplit(page_url).path)
    ):
        signals.append(
            IssueSignal(
                "job_posting_not_detail_page",
                "structured_data",
                "medium",
                "JobPosting-schema staat niet op een individuele vacaturepagina",
                (
                    "Google verwacht JobPosting-schema op een afzonderlijke detailpagina, "
                    "niet op een vacature-overzicht."
                ),
                "Verplaats of beperk het JobPosting-schema tot individuele, actuele vacatures.",
                {"source": "google_for_jobs", "page_url": page_url},
            )
        )

    recommended = [field for field in ("employmentType", "identifier") if not job.get(field)]
    if recommended:
        field_labels = {
            "employmentType": "het type dienstverband",
            "identifier": "een stabiele vacature-identifier",
        }
        additions = " en ".join(field_labels[field] for field in recommended)
        signals.append(
            IssueSignal(
                "job_posting_missing_recommended_fields",
                "optimization",
                "low",
                "JobPosting kan worden aangevuld",
                f"Optionele velden ontbreken: {', '.join(recommended)}.",
                (
                    f"Overweeg {additions} toe te voegen voor vollediger vacature-schema. "
                    "Deze velden zijn niet verplicht en de verwachte SEO-impact is minimaal."
                ),
                {"missing_fields": recommended, "source": "google_for_jobs"},
                confidence="low",
            )
        )
    return signals


def _looks_like_job_detail_page(page_url: str | None, main_content: str) -> bool:
    if not page_url or not JOB_DETAIL_URL_RE.search(urlsplit(page_url).path):
        return False
    return bool(JOB_TERMS_RE.search(main_content))


def _missing_required_job_fields(job: dict[str, object]) -> list[str]:
    missing: list[str] = []
    if not _string(job.get("title")):
        missing.append("title")
    if not _string(job.get("description")):
        missing.append("description")
    if not _parse_date(job.get("datePosted")):
        missing.append("datePosted")
    if not _organization_name(job.get("hiringOrganization")):
        missing.append("hiringOrganization")
    return missing


def _invalid_job_dates(job: dict[str, object]) -> list[str]:
    invalid: list[str] = []
    date_posted = _parse_date(job.get("datePosted"))
    valid_through = _parse_date(job.get("validThrough"))
    if job.get("datePosted") and date_posted is None:
        invalid.append("datePosted is geen geldige datum")
    if job.get("validThrough") and valid_through is None:
        invalid.append("validThrough is geen geldige datum")
    if date_posted and valid_through and valid_through < date_posted:
        invalid.append("validThrough ligt vóór datePosted")
    return invalid


def _is_remote_job(job: dict[str, object]) -> bool:
    value = _string(job.get("jobLocationType"))
    return value is not None and value.upper() == "TELECOMMUTE"


def _job_location_missing_country(value: object) -> bool:
    locations = value if isinstance(value, list) else [value]
    for location in locations:
        if not isinstance(location, dict):
            return True
        address = location.get("address")
        if not isinstance(address, dict) or not _string(address.get("addressCountry")):
            return True
    return False


def recognize_job_listing(
    schema_data: list[object],
    *,
    page_url: str,
    title: str | None,
    headings: dict[str, list[str]] | None,
    main_content: str | None,
    status_code: int | None,
    redirect_chain: list[dict[str, object]] | None,
    application_url: str | None,
    today: date | None = None,
) -> RecognizedJobListing | None:
    """Identify one vacancy and normalize the useful JobPosting fields."""
    today = today or datetime.now(UTC).date()
    jobs = list(_find_job_postings(schema_data))
    path = urlsplit(page_url).path
    sources: list[str] = []
    job: dict[str, object] = {}
    if jobs:
        job = jobs[0]
        sources.append("job_posting_schema")
    if JOB_DETAIL_URL_RE.search(path):
        sources.append("url_pattern")
    visible_text = " ".join([title or "", *(headings or {}).get("h1", []), main_content or ""])
    if JOB_TERMS_RE.search(visible_text):
        sources.append("page_text")
    if not sources or (not jobs and "url_pattern" not in sources):
        return None

    valid_through = _parse_date(job.get("validThrough"))
    visible_closing_date = _visible_closing_date(main_content or "")
    lifecycle_status = _job_lifecycle_status(
        status_code=status_code,
        redirect_chain=redirect_chain,
        valid_through=valid_through,
        visible_closing_date=visible_closing_date,
        today=today,
    )
    schema_title = _string(job.get("title"))
    return RecognizedJobListing(
        detection_sources=sources,
        title=schema_title or _first_headline(headings) or title,
        employer=_organization_name(job.get("hiringOrganization")),
        locations=_job_locations(job.get("jobLocation")),
        date_posted=_parse_date(job.get("datePosted")),
        valid_through=valid_through or visible_closing_date,
        salary_data=_salary_data(job.get("baseSalary")),
        hours=_string(job.get("workHours")),
        employment_types=_strings(job.get("employmentType")),
        external_identifier=_identifier(job.get("identifier")),
        application_url=application_url,
        job_posting_data=job,
        lifecycle_status=lifecycle_status,
    )


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


def _visible_closing_date(content: str) -> date | None:
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
    return parsed


def _visible_expired_deadline(content: str, today: date) -> date | None:
    parsed = _visible_closing_date(content)
    return parsed if parsed and parsed < today else None


def _job_lifecycle_status(
    *,
    status_code: int | None,
    redirect_chain: list[dict[str, object]] | None,
    valid_through: date | None,
    visible_closing_date: date | None,
    today: date,
) -> str:
    if redirect_chain:
        return "redirected"
    if status_code in {404, 410}:
        return "removed"
    deadline = valid_through or visible_closing_date
    if deadline and deadline < today:
        return "expired"
    if deadline and deadline <= today + timedelta(days=14):
        return "expiring_soon"
    return "active"


def _string(value: object) -> str | None:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _strings(value: object) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [item for item in (_string(value) for value in values) if item]


def _first_headline(headings: dict[str, list[str]] | None) -> str | None:
    if not headings:
        return None
    return next((value for value in headings.get("h1", []) if value), None)


def _organization_name(value: object) -> str | None:
    return _string(value.get("name")) if isinstance(value, dict) else _string(value)


def _job_locations(value: object) -> list[str]:
    locations = value if isinstance(value, list) else [value]
    values: list[str] = []
    for location in locations:
        if not isinstance(location, dict):
            text = _string(location)
            if text:
                values.append(text)
            continue
        address = location.get("address")
        if isinstance(address, dict):
            parts = [
                _string(address.get(field))
                for field in ("streetAddress", "addressLocality", "addressRegion", "addressCountry")
            ]
            text = ", ".join(part for part in parts if part)
        else:
            text = _string(address)
        if text:
            values.append(text)
    return list(dict.fromkeys(values))


def _salary_data(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _identifier(value: object) -> str | None:
    if isinstance(value, dict):
        return _string(value.get("value")) or _string(value.get("name"))
    return _string(value)


def _expiration_description(evidence: dict[str, object]) -> str:
    details: list[str] = []
    if "validThrough" in evidence:
        details.append(f"validThrough ({evidence['validThrough']}) ligt in het verleden")
    if "visible_closing_date" in evidence:
        details.append(
            f"zichtbare sluitingsdatum ({evidence['visible_closing_date']}) ligt in het verleden"
        )
    if evidence.get("application_cta_active"):
        details.append("de sollicitatie-CTA is nog actief")
    return "; ".join(details) + "."

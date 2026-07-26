from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.discovery import Url
from app.models.issues import Issue, IssueOccurrence
from app.services.issue_engine import reconcile_issues
from app.services.technical_checks import IssueSignal

SERVER_ERROR_INCIDENT_TYPE = "server_error_incident"
MINIMUM_INCIDENT_SIZE = 3


def analyze_server_error_incident(
    db: Session, *, website_id: object, crawl_run_id: object
) -> list[Issue]:
    """Group concurrent 5xx responses as one incident requiring confirmation."""
    rows = list(
        db.execute(
            select(Issue, Url, IssueOccurrence)
            .join(Url, Url.id == Issue.url_id)
            .join(IssueOccurrence, IssueOccurrence.issue_id == Issue.id)
            .where(
                Issue.website_id == website_id,
                Issue.issue_type == "http_5xx",
                IssueOccurrence.crawl_run_id == crawl_run_id,
            )
            .order_by(Url.normalized_url)
        )
    )
    urls_by_status: dict[int, set[str]] = defaultdict(set)
    for _issue, url, occurrence in rows:
        status_code = occurrence.evidence.get("status_code")
        if isinstance(status_code, int) and 500 <= status_code <= 599:
            urls_by_status[status_code].add(url.normalized_url)

    incidents: list[dict[str, object]] = []
    affected_urls: set[str] = set()
    for status_code, urls in sorted(urls_by_status.items()):
        if len(urls) < MINIMUM_INCIDENT_SIZE:
            continue
        sorted_urls = sorted(urls)
        affected_urls.update(sorted_urls)
        incidents.append(
            {
                "status_code": status_code,
                "url_count": len(sorted_urls),
                "urls": sorted_urls,
                "examples": sorted_urls[:10],
            }
        )

    signals: list[IssueSignal] = []
    if incidents:
        signals.append(
            IssueSignal(
                issue_type=SERVER_ERROR_INCIDENT_TYPE,
                category="reachability",
                severity="high",
                confidence="medium",
                title=(
                    f"Mogelijk serverincident raakt {len(affected_urls)} URL's"
                ),
                description=(
                    "Meerdere URL's gaven tijdens dezelfde crawl een vergelijkbare serverfout. "
                    "Dit kan één tijdelijk beschikbaarheidsincident zijn en is daarom geen "
                    "afzonderlijke onderhoudstaak per URL."
                ),
                recommended_action=(
                    "Controleer hosting- en applicatielogs rond het crawltijdstip en bevestig de "
                    "betrokken URL's met een nieuwe light check. Onderzoek afzonderlijke pagina's "
                    "pas wanneer de fout daarna terugkomt."
                ),
                evidence={
                    "affected_url_count": len(affected_urls),
                    "incident_count": len(incidents),
                    "patterns": incidents,
                    "likely_cause": (
                        "Een gedeelde applicatie-, proxy- of hostingstoring heeft waarschijnlijk "
                        "meerdere requests in hetzelfde crawlvenster geraakt."
                    ),
                    "alternative_explanation": (
                        "De URL's kunnen onafhankelijk dezelfde foutstatus geven; een hercontrole "
                        "bepaalt of het incident tijdelijk of structureel is."
                    ),
                    "verification": (
                        "een nieuwe light check geeft voor alle betrokken URL's een stabiele "
                        "niet-5xx-status"
                    ),
                },
            )
        )
    return reconcile_issues(
        db,
        website_id=website_id,
        url_id=None,
        crawl_run_id=crawl_run_id,
        snapshot_id=None,
        signals=signals,
        checked_issue_types={SERVER_ERROR_INCIDENT_TYPE},
    )

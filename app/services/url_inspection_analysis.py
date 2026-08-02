from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crawl import UrlSnapshot
from app.models.discovery import Url, UrlSource
from app.models.integrations import UrlInspectionResult
from app.models.issues import Change, Issue
from app.services.issue_engine import reconcile_issues
from app.services.technical_checks import IssueSignal
from app.services.url_normalization import InvalidUrlError, normalize_url

URL_INSPECTION_ISSUE_TYPES = {
    "google_not_indexed",
    "google_canonical_mismatch",
    "google_robots_blocked",
    "google_fetch_failed",
}


def analyze_url_inspection_result(
    db: Session, result: UrlInspectionResult
) -> list[Issue]:
    url = db.get(Url, result.url_id)
    if url is None:
        raise ValueError("URL Inspection URL does not exist")
    snapshot = db.scalar(
        select(UrlSnapshot)
        .where(UrlSnapshot.url_id == result.url_id)
        .order_by(UrlSnapshot.checked_at.desc())
        .limit(1)
    )
    if snapshot is None:
        return []
    in_sitemap = (
        db.scalar(
            select(UrlSource.id)
            .where(UrlSource.url_id == url.id, UrlSource.source_type == "sitemap")
            .limit(1)
        )
        is not None
    )
    intended_for_indexing = bool(
        snapshot.status_code == 200
        and snapshot.is_indexable is not False
        and (url.is_important or in_sitemap)
    )
    signals: list[IssueSignal] = []
    evidence = _evidence(result, snapshot=snapshot, in_sitemap=in_sitemap)
    google_evidence_is_stale = _google_observation_predates_relevant_change(db, result)
    if (
        intended_for_indexing
        and result.verdict
        and result.verdict != "PASS"
        and not google_evidence_is_stale
    ):
        signals.append(
            _signal(
                "google_not_indexed",
                "high",
                "Belangrijke pagina staat niet bevestigd in Google",
                "Controleer de dekkingsreden, interne vindbaarheid, sitemap en canonical en vraag "
                "na herstel een nieuwe Google-crawl aan.",
                evidence,
            )
        )
    if (
        intended_for_indexing
        and result.robots_txt_state == "DISALLOWED"
        and not google_evidence_is_stale
    ):
        signals.append(
            _signal(
                "google_robots_blocked",
                "high",
                "Google meldt een robots.txt-blokkade",
                "Controleer de robots.txt-regels voor Googlebot en maak de belangrijke URL "
                "crawlbaar wanneer deze in Google moet verschijnen.",
                evidence,
            )
        )
    if (
        intended_for_indexing
        and result.page_fetch_state
        and result.page_fetch_state not in {"SUCCESSFUL", "PAGE_FETCH_STATE_UNSPECIFIED"}
        and not google_evidence_is_stale
    ):
        signals.append(
            _signal(
                "google_fetch_failed",
                "high",
                "Google kon de pagina niet ophalen",
                "Onderzoek Googles fetchstatus naast serverlogs, robotsregels en actuele "
                "bereikbaarheid; herstel het verschil en laat Google opnieuw crawlen.",
                evidence,
            )
        )
    declared_canonical = snapshot.canonical or snapshot.final_url or snapshot.requested_url
    if (
        intended_for_indexing
        and result.google_canonical
        and _normalized(result.google_canonical) != _normalized(declared_canonical)
        and not google_evidence_is_stale
    ):
        signals.append(
            _signal(
                "google_canonical_mismatch",
                "medium",
                "Google kiest een andere canonical",
                "Vergelijk inhoud, interne links, redirects, sitemap en canonicalsignalen van "
                "beide URL's en maak de gewenste primaire URL eenduidig.",
                evidence,
            )
        )
    return reconcile_issues(
        db,
        website_id=result.website_id,
        url_id=result.url_id,
        crawl_run_id=snapshot.crawl_run_id,
        snapshot_id=snapshot.id,
        signals=signals,
        checked_issue_types=URL_INSPECTION_ISSUE_TYPES,
    )


def _google_observation_predates_relevant_change(
    db: Session, result: UrlInspectionResult
) -> bool:
    if result.last_crawl_time is None:
        return False
    latest_change = db.scalar(
        select(Change.detected_at)
        .where(
            Change.url_id == result.url_id,
            Change.change_type.in_(
                {
                    "canonical_changed",
                    "indexability_changed",
                    "robots_changed",
                    "status_code_changed",
                }
            ),
        )
        .order_by(Change.detected_at.desc())
        .limit(1)
    )
    return bool(latest_change and _as_utc(latest_change) > _as_utc(result.last_crawl_time))


def _evidence(
    result: UrlInspectionResult, *, snapshot: UrlSnapshot, in_sitemap: bool
) -> dict[str, object]:
    return {
        "source": "google_url_inspection",
        "inspected_at": result.inspected_at.isoformat(),
        "google_last_crawl_time": (
            result.last_crawl_time.isoformat() if result.last_crawl_time else None
        ),
        "verdict": result.verdict,
        "coverage_state": result.coverage_state,
        "robots_txt_state": result.robots_txt_state,
        "page_fetch_state": result.page_fetch_state,
        "google_canonical": result.google_canonical,
        "user_canonical": result.user_canonical,
        "crawler_canonical": snapshot.canonical,
        "in_sitemap": in_sitemap,
    }


def _normalized(value: str) -> str:
    try:
        return normalize_url(value)
    except InvalidUrlError:
        return value


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _signal(
    issue_type: str,
    severity: str,
    title: str,
    action: str,
    evidence: dict[str, object],
) -> IssueSignal:
    return IssueSignal(
        issue_type=issue_type,
        category="indexation",
        severity=severity,
        title=title,
        description=(
            f"{title}. Dit is gebaseerd op de nieuwste Google URL Inspection-observatie en de "
            "actuele crawlergegevens."
        ),
        recommended_action=action,
        evidence=evidence,
    )

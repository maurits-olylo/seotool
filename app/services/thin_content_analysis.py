from collections import defaultdict
from statistics import median
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crawl import UrlSnapshot
from app.models.discovery import Url
from app.models.issues import Issue
from app.services.issue_engine import reconcile_issues
from app.services.technical_checks import (
    THIN_CONTENT_WORD_LIMIT,
    IssueSignal,
    is_functional_page_url,
)

MINIMUM_FAMILY_SIZE = 5
MINIMUM_SITE_SIZE = 10
MAXIMUM_BASELINE_RATIO = 0.5


def analyze_contextual_thin_content(
    db: Session, *, website_id: object, crawl_run_id: object
) -> list[Issue]:
    """Report limited content only when it is exceptional within the current site."""
    rows = list(
        db.execute(
            select(Url, UrlSnapshot)
            .join(UrlSnapshot, UrlSnapshot.url_id == Url.id)
            .where(
                Url.website_id == website_id,
                UrlSnapshot.crawl_run_id == crawl_run_id,
            )
            .order_by(Url.normalized_url)
        )
    )
    comparable = [
        (url, snapshot)
        for url, snapshot in rows
        if _is_comparable(url, snapshot)
    ]
    site_counts = [snapshot.word_count or 0 for _url, snapshot in comparable]
    family_counts: dict[str, list[int]] = defaultdict(list)
    for url, snapshot in comparable:
        family_counts[_url_family(url.normalized_url)].append(snapshot.word_count or 0)

    touched: list[Issue] = []
    for url, snapshot in rows:
        signals: list[IssueSignal] = []
        if _is_nearly_empty_actionable(url, snapshot):
            signals.append(
                IssueSignal(
                    issue_type="thin_content",
                    category="onpage",
                    severity="medium",
                    confidence="medium",
                    title="Nagenoeg lege pagina",
                    description=(
                        "Deze indexeerbare pagina bevat vrijwel geen hoofdcontent en is geen "
                        "herkende functionele pagina."
                    ),
                    recommended_action=(
                        "Controleer of de pagina bewust leeg is. Voeg inhoud toe, maak de pagina "
                        "niet-indexeerbaar of herstel de contentextractie."
                    ),
                    evidence={
                        "word_count": snapshot.word_count,
                        "threshold": 30,
                        "content_level": "nearly_empty",
                    },
                )
            )
        elif _is_contextual_outlier(
            url,
            snapshot,
            site_counts=site_counts,
            family_counts=family_counts,
        ):
            family = _url_family(url.normalized_url)
            cohort = family_counts.get(family, [])
            baseline_scope = "url_family" if len(cohort) >= MINIMUM_FAMILY_SIZE else "website"
            baseline_counts = cohort if baseline_scope == "url_family" else site_counts
            baseline = float(median(baseline_counts))
            signals.append(
                IssueSignal(
                    issue_type="thin_content",
                    category="onpage",
                    severity="low",
                    confidence="medium",
                    title="Hoofdcontent wijkt sterk af van vergelijkbare pagina's",
                    description=(
                        "Deze indexeerbare pagina bevat duidelijk minder hoofdcontent dan "
                        "vergelijkbare pagina's binnen dezelfde website."
                    ),
                    recommended_action=(
                        "Controleer of de pagina dezelfde zoekintentie en informatiewaarde heeft "
                        "als vergelijkbare pagina's. Vul alleen aan wanneer de afwijking "
                        "onbedoeld is."
                    ),
                    evidence={
                        "word_count": snapshot.word_count,
                        "threshold": THIN_CONTENT_WORD_LIMIT,
                        "content_level": "contextual_outlier",
                        "baseline_scope": baseline_scope,
                        "baseline_word_count": round(baseline, 1),
                        "baseline_ratio": round((snapshot.word_count or 0) / baseline, 3),
                        "cohort_size": len(baseline_counts),
                        "url_family": family,
                    },
                )
            )
        touched.extend(
            reconcile_issues(
                db,
                website_id=website_id,
                url_id=url.id,
                crawl_run_id=crawl_run_id,
                snapshot_id=snapshot.id,
                signals=signals,
                checked_issue_types={"thin_content"},
            )
        )
    return touched


def _is_nearly_empty_actionable(url: Url, snapshot: UrlSnapshot) -> bool:
    page_url = snapshot.final_url or url.normalized_url
    return bool(
        snapshot.status_code == 200
        and not snapshot.redirect_chain
        and snapshot.is_indexable is True
        and snapshot.word_count is not None
        and snapshot.word_count < 30
        and not is_functional_page_url(page_url)
    )


def _is_comparable(url: Url, snapshot: UrlSnapshot) -> bool:
    page_url = snapshot.final_url or url.normalized_url
    return bool(
        snapshot.status_code == 200
        and not snapshot.redirect_chain
        and snapshot.is_indexable is True
        and snapshot.word_count is not None
        and snapshot.word_count >= 30
        and not is_functional_page_url(page_url)
    )


def _is_contextual_outlier(
    url: Url,
    snapshot: UrlSnapshot,
    *,
    site_counts: list[int],
    family_counts: dict[str, list[int]],
) -> bool:
    if not _is_comparable(url, snapshot):
        return False
    word_count = snapshot.word_count or 0
    if word_count >= THIN_CONTENT_WORD_LIMIT:
        return False
    family = family_counts.get(_url_family(url.normalized_url), [])
    if len(family) >= MINIMUM_FAMILY_SIZE:
        baseline_counts = family
    elif len(site_counts) >= MINIMUM_SITE_SIZE:
        baseline_counts = site_counts
    else:
        return bool(url.is_important)
    baseline = float(median(baseline_counts))
    return baseline >= THIN_CONTENT_WORD_LIMIT and (
        url.is_important or word_count <= baseline * MAXIMUM_BASELINE_RATIO
    )


def _url_family(url: str) -> str:
    parts = [part for part in urlsplit(url).path.strip("/").split("/") if part]
    return f"/{parts[0]}" if parts else "/"

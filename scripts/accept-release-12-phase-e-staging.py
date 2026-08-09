import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.content_analysis import UrlContentClassification
from app.models.discovery import Url
from app.models.integrations import MatomoPageMetric
from app.models.opportunities import OpportunityEvaluation
from app.models.website import Website, WebsiteSettings
from app.services.opportunity_engine import evaluate_website_opportunities
from app.services.opportunity_testability import (
    detect_underperforming_winners,
    device_friction_candidate,
    intent_mismatch_candidates,
)

PERIOD_START = date(2026, 7, 1)
PERIOD_END = date(2026, 7, 28)
BASE_URL = "https://release-12-testability.invalid"


def _page(db, website_id, index: int) -> Url:
    value = f"{BASE_URL}/journey-{index}"
    url = db.scalar(
        select(Url).where(Url.website_id == website_id, Url.normalized_url == value)
    )
    if url is None:
        url = Url(website_id=website_id, normalized_url=value)
        db.add(url)
        db.flush()
    url.current_status_code = 200
    url.current_final_url = value
    url.is_active = True
    url.is_indexable = True
    url.page_type = "staging_acceptance"
    return url


def _classification(db, url: Url, index: int) -> None:
    classification = db.scalar(
        select(UrlContentClassification).where(
            UrlContentClassification.url_id == url.id,
            UrlContentClassification.classification_version == "release-12-phase-e",
        )
    )
    if classification is None:
        db.add(
            UrlContentClassification(
                website_id=url.website_id,
                url_id=url.id,
                period_start=PERIOD_START,
                period_end=PERIOD_END,
                input_hash=f"{index + 100:064d}",
                classification_version="release-12-phase-e",
                search_intent="informational",
                journey_stage="understand",
                content_role="attract",
                confidence=0.9,
                probabilities={"informational": 1.0},
                source_coverage={"staging_fixture": True},
                evidence=[],
            )
        )


def _metric(db, url: Url, index: int) -> None:
    metric = db.scalar(
        select(MatomoPageMetric).where(
            MatomoPageMetric.website_id == url.website_id,
            MatomoPageMetric.date == date(2026, 7, 15),
            MatomoPageMetric.page_url == url.normalized_url,
        )
    )
    if metric is None:
        metric = MatomoPageMetric(
            website_id=url.website_id,
            url_id=url.id,
            date=date(2026, 7, 15),
            page_url=url.normalized_url,
        )
        db.add(metric)
    visits = 25 if index == 0 else 40
    bounces = 25 if index == 0 else 32
    metric.visits = visits
    metric.pageviews = visits
    metric.unique_pageviews = visits
    metric.entry_visits = visits
    metric.bounces = bounces
    metric.exits = bounces
    metric.conversions = 0


def _factor(evaluation: OpportunityEvaluation, signal: str) -> dict[str, object]:
    return next(item for item in evaluation.contributors if item.get("signal") == signal)


def _assert_candidate_boundaries() -> None:
    pages = [
        {"url_id": "winner", "content_role": "convert", "visits": 200, "conversions": 0},
        {"url_id": "peer", "content_role": "convert", "visits": 800, "conversions": 20},
    ]
    if len(detect_underperforming_winners(pages, {"winner": 500})) != 1:
        raise RuntimeError("Underperforming winner was not recognized")
    mismatch = intent_mismatch_candidates(
        [
            {
                "url_id": "page",
                "query": "wat kost isolatie",
                "intent": "prijs",
                "impressions": 300,
                "clicks": 10,
                "coverage_status": "partial",
            }
        ],
        {"page": "informational"},
    )
    if len(mismatch) != 1:
        raise RuntimeError("Intent mismatch was not recognized")
    if device_friction_candidate(
        url_id="page", mobile_volume=None, mobile_score=0.4, desktop_score=0.8
    ) is not None:
        raise RuntimeError("Device candidate ignored missing mobile volume")


def _assert_user_interface() -> None:
    source = (Path(__file__).resolve().parents[1] / "app/ui/app.js").read_text()
    required = (
        'journey_friction: "Mogelijke doorstroomkans"',
        'testable: "Test overwegen"',
        'journey_behavior: "Bezoekersgedrag"',
        'needs_hypothesis_review: "Hypothese beoordelen"',
    )
    if not all(value in source for value in required):
        raise RuntimeError("Testability interface labels are incomplete")


def main() -> None:
    _assert_candidate_boundaries()
    _assert_user_interface()
    with SessionLocal() as db:
        website = db.scalar(
            select(Website).where(Website.name.like("[STAGING]%")).order_by(Website.created_at)
        )
        if website is None:
            raise RuntimeError("No synthetic staging website exists")
        settings = db.get(WebsiteSettings, website.id)
        if settings is None:
            raise RuntimeError("Synthetic staging website has no settings")
        original_source = settings.primary_analytics_source
        pages = []
        for index in range(6):
            url = _page(db, website.id, index)
            _classification(db, url, index)
            _metric(db, url, index)
            pages.append(url)
        settings.primary_analytics_source = "matomo"
        db.commit()
        try:
            evaluate_website_opportunities(db, website.id, PERIOD_START, PERIOD_END)
        finally:
            settings.primary_analytics_source = original_source
            db.commit()
        evaluation = db.scalar(
            select(OpportunityEvaluation)
            .where(
                OpportunityEvaluation.website_id == website.id,
                OpportunityEvaluation.scope_key == f"journey_friction:{pages[0].id}",
            )
            .order_by(OpportunityEvaluation.created_at.desc())
        )
        if evaluation is None:
            raise RuntimeError("Journey test candidate was not stored")
        if _factor(evaluation, "testability_band")["value"] != "effect_measurement_preferred":
            raise RuntimeError("Unexpected testability advice")
        if _factor(evaluation, "impact_domains")["value"] != ["SEO", "UX", "conversie"]:
            raise RuntimeError("Cross-domain journey impact is incomplete")
        print(
            {
                "status": "release_12_phase_e_staging_ok",
                "journey_opportunity_id": str(evaluation.id),
                "testability_band": "effect_measurement_preferred",
                "false_device_candidate": False,
                "source_restored": settings.primary_analytics_source == original_source,
            }
        )


if __name__ == "__main__":
    main()

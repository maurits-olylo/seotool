from datetime import date

from sqlalchemy import func, select

from app.core.security import Principal
from app.db.session import SessionLocal
from app.models.client import Client
from app.models.content_analysis import (
    QueryContentClassification,
    UrlContentClassification,
    UrlContentOverride,
)
from app.models.discovery import Url
from app.models.integrations import SearchConsoleQueryMetric
from app.models.recommendations import RecommendationTask
from app.models.website import Website, WebsiteSettings
from app.services.content_analysis import CLASSIFICATION_VERSION
from app.services.content_opportunities import (
    build_content_opportunities,
    create_opportunity_task,
)


def _classification(website_id, url_id, intent: str) -> UrlContentClassification:  # type: ignore[no-untyped-def]
    return UrlContentClassification(
        website_id=website_id,
        url_id=url_id,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 7),
        input_hash=str(url_id).replace("-", "").ljust(64, "0")[:64],
        classification_version=CLASSIFICATION_VERSION,
        search_intent=intent,
        journey_stage="compare",
        content_role="support_choice",
        confidence=0.8,
        probabilities={intent: 1.0},
        source_coverage={"crawl": True, "gsc_queries": True},
        evidence=[{"source": "test"}],
    )


def test_distributions_mismatch_overlap_and_task_deduplication() -> None:
    with SessionLocal() as db:
        client = Client(name="Opportunity customer")
        website = Website(
            client=client,
            name="Opportunity site",
            base_url="https://example.com",
            language="nl",
            country="NL",
        )
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        first = Url(
            website_id=website.id,
            normalized_url="https://example.com/diensten/eerste",
            current_status_code=200,
            is_indexable=True,
        )
        second = Url(
            website_id=website.id,
            normalized_url="https://example.com/diensten/tweede",
            current_status_code=200,
            is_indexable=True,
        )
        db.add_all([first, second])
        db.flush()
        db.add_all(
            [
                _classification(website.id, first.id, "commercial"),
                _classification(website.id, second.id, "commercial"),
                UrlContentOverride(
                    website_id=website.id,
                    url_id=first.id,
                    search_intent="transactional",
                    is_locked=True,
                    rationale="Manual review",
                ),
                SearchConsoleQueryMetric(
                    website_id=website.id,
                    url_id=first.id,
                    date=date(2026, 8, 3),
                    query="beste warmtepomp",
                    page_url=first.normalized_url,
                    clicks=8,
                    impressions=100,
                    ctr=0.08,
                    position=5,
                ),
                SearchConsoleQueryMetric(
                    website_id=website.id,
                    url_id=second.id,
                    date=date(2026, 8, 3),
                    query="beste warmtepomp",
                    page_url=second.normalized_url,
                    clicks=5,
                    impressions=60,
                    ctr=0.083,
                    position=7,
                ),
                QueryContentClassification(
                    normalized_query="koop warmtepomp",
                    language="nl",
                    country="NL",
                    classification_version=CLASSIFICATION_VERSION,
                    input_hash="c" * 64,
                    search_intent="transactional",
                    journey_stage="act",
                    content_role="convert",
                    confidence=0.9,
                    probabilities={"transactional": 1.0},
                    evidence=[{"source": "query_terms"}],
                ),
                SearchConsoleQueryMetric(
                    website_id=website.id,
                    url_id=second.id,
                    date=date(2026, 8, 3),
                    query="koop warmtepomp",
                    page_url=second.normalized_url,
                    clicks=4,
                    impressions=80,
                    ctr=0.05,
                    position=9,
                ),
            ]
        )
        db.commit()

        result = build_content_opportunities(db, website.id, date(2026, 8, 1), date(2026, 8, 7))
        assert result["coverage"] == {"classified_pages": 2, "pages_with_gsc": 2}
        assert result["website_distribution"] == {"commercial": 1, "transactional": 1}
        assert result["cluster_distribution"] == {"diensten": {"commercial": 1, "transactional": 1}}
        opportunities = result["opportunities"]
        assert {item["type"] for item in opportunities} == {
            "content_gap",
            "intent_mismatch",
            "query_overlap",
        }

        overlap = next(item for item in opportunities if item["type"] == "query_overlap")
        principal = Principal(user_id=None, role="superuser", is_api_key=True)
        first_task, created = create_opportunity_task(
            db, website_id=website.id, opportunity=overlap, principal=principal
        )
        repeated_task, repeated_created = create_opportunity_task(
            db, website_id=website.id, opportunity=overlap, principal=principal
        )
        assert created is True
        assert repeated_created is False
        assert repeated_task.id == first_task.id
        assert db.scalar(select(func.count()).select_from(RecommendationTask)) == 1


def test_low_volume_or_uncertain_overlap_is_not_an_opportunity() -> None:
    with SessionLocal() as db:
        client = Client(name="Quiet customer")
        website = Website(client=client, name="Quiet site", base_url="https://quiet.example.com")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        url = Url(website_id=website.id, normalized_url="https://quiet.example.com/page")
        db.add(url)
        db.flush()
        db.add(_classification(website.id, url.id, "uncertain"))
        db.commit()
        result = build_content_opportunities(db, website.id, date(2026, 8, 1), date(2026, 8, 7))
        assert result["opportunities"] == []

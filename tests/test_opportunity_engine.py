from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.content_analysis import UrlContentClassification
from app.models.discovery import Url
from app.models.integrations import SearchConsoleMetric
from app.models.issues import Issue
from app.models.opportunities import OpportunityEvaluation
from app.models.website import Website
from app.services.opportunity_engine import evaluate_website_opportunities


def _metric(url: Url, day: date, *, impressions: int, clicks: float, position: float):
    return SearchConsoleMetric(
        website_id=url.website_id,
        url_id=url.id,
        date=day,
        page_url=url.normalized_url,
        clicks=clicks,
        impressions=impressions,
        ctr=clicks / impressions,
        position=position,
    )


def _issue(url: Url, issue_type: str, *, status: str = "new") -> Issue:
    return Issue(
        website_id=url.website_id,
        url_id=url.id,
        issue_type=issue_type,
        category="content",
        severity="medium",
        confidence="high",
        status=status,
        title=issue_type,
        description="Evidence",
        recommended_action="Review",
    )


def test_engine_prioritizes_important_accessibility_page_without_search_data() -> None:
    with SessionLocal() as db:
        customer = Client(name="Cross-domain priority")
        website = Website(
            client=customer,
            name="Cross-domain priority site",
            base_url="https://priority.example.com",
        )
        db.add(website)
        db.flush()
        page = Url(
            website_id=website.id,
            normalized_url="https://priority.example.com/contact",
            current_status_code=200,
            is_active=True,
            is_indexable=True,
            is_important=True,
        )
        db.add(page)
        db.flush()
        issue = _issue(page, "accessibility_label")
        issue.category = "accessibility"
        issue.severity = "high"
        db.add(issue)
        db.commit()

        result = evaluate_website_opportunities(
            db,
            website.id,
            date(2026, 7, 1),
            date(2026, 7, 28),
        )
        evaluation = db.scalar(select(OpportunityEvaluation))

        assert result == {"created": 1, "existing": 0, "skipped": 0}
        assert evaluation is not None
        assert evaluation.source_coverage == {
            "gsc": False,
            "crawler_issues": True,
            "analytics": False,
            "pattern": "important_accessibility",
        }
        factors = {item["signal"]: item for item in evaluation.contributors if "label" in item}
        assert factors["priority_summary"]["value"] == (
            "Impact op SEO en toegankelijkheid; belangrijke pagina."
        )
        assert factors["evidence_completeness"]["missing_sources"] == ["zoekprestatie"]
        assert factors["important_page_context"]["value"] == {
            "important_url": True,
            "observed_demand": 0,
        }


def test_engine_combines_potential_and_matching_friction_without_duplicates() -> None:
    with SessionLocal() as db:
        customer = Client(name="Opportunity engine")
        website = Website(
            client=customer,
            name="Opportunity engine site",
            base_url="https://opportunities.example.com",
        )
        db.add(website)
        db.flush()
        ctr_page = Url(
            website_id=website.id,
            normalized_url="https://opportunities.example.com/ctr",
            current_status_code=200,
            is_active=True,
            is_indexable=True,
            crawl_depth=2,
        )
        page_two = Url(
            website_id=website.id,
            normalized_url="https://opportunities.example.com/page-two",
            current_status_code=200,
            is_active=True,
            is_indexable=True,
            crawl_depth=2,
        )
        deep_page = Url(
            website_id=website.id,
            normalized_url="https://opportunities.example.com/deep",
            current_status_code=200,
            is_active=True,
            is_indexable=True,
            crawl_depth=5,
        )
        db.add_all([ctr_page, page_two, deep_page])
        db.flush()
        start = date(2026, 7, 1)
        for offset in range(28):
            day = start + timedelta(days=offset)
            db.add_all(
                [
                    _metric(ctr_page, day, impressions=20, clicks=0.2, position=7),
                    _metric(page_two, day, impressions=10, clicks=0.3, position=14),
                    _metric(deep_page, day, impressions=8, clicks=0.4, position=8),
                ]
            )
        db.add_all(
            [
                _issue(ctr_page, "missing_meta_description"),
                _issue(page_two, "thin_content"),
                _issue(deep_page, "important_page_few_internal_links"),
                UrlContentClassification(
                    website_id=website.id,
                    url_id=page_two.id,
                    period_start=start,
                    period_end=start + timedelta(days=27),
                    input_hash="a" * 64,
                    classification_version="test-v1",
                    search_intent="informational",
                    journey_stage="understand",
                    content_role="attract",
                    confidence=0.8,
                    probabilities={"informational": 1.0},
                    source_coverage={"crawler": True},
                    evidence=[],
                ),
            ]
        )
        db.commit()

        first = evaluate_website_opportunities(db, website.id, start, start + timedelta(days=27))
        second = evaluate_website_opportunities(db, website.id, start, start + timedelta(days=27))
        evaluations = list(db.scalars(select(OpportunityEvaluation)))

        assert first == {"created": 3, "existing": 0, "skipped": 0}
        assert second == {"created": 0, "existing": 3, "skipped": 0}
        assert {item.source_coverage["pattern"] for item in evaluations} == {
            "ctr",
            "page_two",
            "internal_link",
        }
        assert all(item.total_score is not None for item in evaluations)
        assert all(item.contributors and item.evidence for item in evaluations)


def test_engine_rejects_false_opportunities_and_short_periods() -> None:
    with SessionLocal() as db:
        customer = Client(name="Opportunity filters")
        website = Website(
            client=customer,
            name="Opportunity filter site",
            base_url="https://filters.example.com",
        )
        db.add(website)
        db.flush()
        search_page = Url(
            website_id=website.id,
            normalized_url="https://filters.example.com/search?q=test",
            current_status_code=200,
            is_active=True,
            is_indexable=True,
            crawl_depth=5,
        )
        ignored_page = Url(
            website_id=website.id,
            normalized_url="https://filters.example.com/ignored",
            current_status_code=200,
            is_active=True,
            is_indexable=True,
            crawl_depth=5,
        )
        db.add_all([search_page, ignored_page])
        db.flush()
        start = date(2026, 7, 1)
        for offset in range(28):
            day = start + timedelta(days=offset)
            db.add_all(
                [
                    _metric(search_page, day, impressions=20, clicks=0.2, position=7),
                    _metric(ignored_page, day, impressions=20, clicks=0.2, position=7),
                ]
            )
        db.add_all(
            [
                _issue(search_page, "missing_title"),
                _issue(ignored_page, "missing_title", status="accepted_risk"),
            ]
        )
        db.commit()

        result = evaluate_website_opportunities(db, website.id, start, start + timedelta(days=27))
        assert result["created"] == 0
        assert db.scalar(select(OpportunityEvaluation.id)) is None
        with pytest.raises(ValueError, match="at least 28 days"):
            evaluate_website_opportunities(db, website.id, start, start + timedelta(days=6))

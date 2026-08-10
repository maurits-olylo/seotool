from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.discovery import Url
from app.models.effects import EffectIntervention
from app.models.integrations import SearchConsoleMetric
from app.models.issues import Issue
from app.models.opportunities import OpportunityEvaluation
from app.models.recommendations import RecommendationTask
from app.models.sensor import SensorDailyPageMetric, SensorManifest
from app.models.website import Website
from app.services.effect_analysis import evaluate_effect_cohort
from app.services.opportunity_engine import evaluate_website_opportunities
from app.services.sensor_aggregates import (
    SensorAggregateProvider,
    reconcile_sensor_measurement_state,
    reliable_sensor_evidence_by_url,
)


def _manifest(website_id, *, version: str = "2026-08-10.1"):  # type: ignore[no-untyped-def]
    return SensorManifest(
        website_id=website_id,
        schema_version="1",
        manifest_version=version,
        profile="lead_generation",
        page_match="/offerte",
        observations=[{"key": "quote_form", "kind": "process", "locator": "quote-form"}],
        content_hash="a" * 64,
        status="active",
        valid_from=datetime(2026, 6, 1, tzinfo=UTC),
        expires_at=datetime(2026, 10, 1, tzinfo=UTC),
    )


def _metric(url: Url, metric_date: date, *, rejected: int = 0) -> SensorDailyPageMetric:
    return SensorDailyPageMetric(
        website_id=url.website_id,
        url_id=url.id,
        date=metric_date,
        manifest_version="2026-08-10.1",
        page_sessions=100,
        active_time_buckets={"30_60s": 40},
        exposures=80,
        interactions=30,
        process_starts=20,
        observed_outcomes=5,
        trusted_outcomes=2,
        rejected_count=rejected,
        sampled_count=0,
    )


def _task(website_id):  # type: ignore[no-untyped-def]
    return RecommendationTask(
        website_id=website_id,
        recommendation_type="content_update",
        definition_version="1",
        title="Update",
        category="content",
        status="implemented",
        primary_role="content",
        supporting_roles=[],
        priority="normal",
        priority_reason="Test",
        feasibility="ready",
        action="Update",
        rationale="Test",
        steps=[],
        dependencies=[],
        required_input=[],
        acceptance_criteria=[],
        verification_spec={},
    )


def test_sensor_quality_becomes_reliable_and_provider_returns_canonical_aggregates() -> None:
    with SessionLocal() as db:
        website = Website(
            client=Client(name="Sensor quality"),
            name="Sensor quality site",
            base_url="https://sensor-quality.example",
        )
        db.add(website)
        db.flush()
        url = Url(website_id=website.id, normalized_url="https://sensor-quality.example/offerte")
        db.add_all([url, _manifest(website.id)])
        db.flush()
        start = date(2026, 8, 1)
        db.add_all([_metric(url, start + timedelta(days=offset)) for offset in range(7)])
        db.flush()

        state = reconcile_sensor_measurement_state(
            db, website.id, start, start + timedelta(days=6), expected_pages=1
        )
        duplicate = reconcile_sensor_measurement_state(
            db, website.id, start, start + timedelta(days=6), expected_pages=1
        )
        aggregates = SensorAggregateProvider(db).page_aggregates_between(
            website.id, start, start + timedelta(days=6)
        )

        assert state is duplicate
        assert state.status == "reliable"
        assert state.observed_pages == 1
        assert aggregates[0].page_sessions == 700
        assert aggregates[0].trusted_outcomes == 14
        assert (
            reliable_sensor_evidence_by_url(db, website.id, start, start + timedelta(days=6))[
                url.id
            ]["outcomes"]
            == 49
        )


def test_sensor_quality_rejects_bad_coverage_for_intelligence() -> None:
    with SessionLocal() as db:
        website = Website(
            client=Client(name="Sensor attention"),
            name="Sensor attention site",
            base_url="https://sensor-attention.example",
        )
        db.add(website)
        db.flush()
        url = Url(website_id=website.id, normalized_url="https://sensor-attention.example/offerte")
        db.add_all([url, _manifest(website.id)])
        db.flush()
        db.add(_metric(url, date(2026, 8, 7), rejected=1))
        db.flush()

        state = reconcile_sensor_measurement_state(
            db, website.id, date(2026, 8, 1), date(2026, 8, 7), expected_pages=2
        )

        assert state.status == "attention_needed"
        assert (
            reliable_sensor_evidence_by_url(db, website.id, date(2026, 8, 1), date(2026, 8, 7))
            == {}
        )


def test_reliable_sensor_evidence_enriches_intelligence_without_causal_claim() -> None:
    with SessionLocal() as db:
        website = Website(
            client=Client(name="Sensor intelligence"),
            name="Sensor intelligence site",
            base_url="https://sensor-intelligence.example",
        )
        db.add(website)
        db.flush()
        url = Url(
            website_id=website.id,
            normalized_url="https://sensor-intelligence.example/offerte",
            current_status_code=200,
            is_active=True,
            is_indexable=True,
        )
        db.add_all([url, _manifest(website.id)])
        db.flush()
        start = date(2026, 7, 1)
        for offset in range(28):
            metric_date = start + timedelta(days=offset)
            db.add_all(
                [
                    SearchConsoleMetric(
                        website_id=website.id,
                        url_id=url.id,
                        date=metric_date,
                        page_url=url.normalized_url,
                        clicks=0.2,
                        impressions=20,
                        ctr=0.05,
                        position=8,
                    ),
                    _metric(url, metric_date),
                ]
            )
        db.add(
            Issue(
                website_id=website.id,
                url_id=url.id,
                issue_type="missing_title",
                category="content",
                severity="medium",
                confidence="high",
                status="new",
                title="Missing title",
                description="Evidence",
                recommended_action="Review",
            )
        )
        db.flush()
        state = reconcile_sensor_measurement_state(
            db, website.id, start, start + timedelta(days=27), expected_pages=1
        )
        assert state.status == "reliable"

        evaluate_website_opportunities(db, website.id, start, start + timedelta(days=27))
        opportunity = db.scalar(
            select(OpportunityEvaluation).where(OpportunityEvaluation.scope_key.like("ctr:%"))
        )
        assert opportunity is not None
        assert opportunity.source_coverage["behavior_observation"] is True
        assert any(item.get("signal") == "observed_behavior" for item in opportunity.contributors)

        task = _task(website.id)
        db.add(task)
        db.flush()
        change_date = date(2026, 8, 1)
        db.add(
            EffectIntervention(
                website_id=website.id,
                task_id=task.id,
                implemented_at=datetime(2026, 8, 1, tzinfo=UTC),
                intervention_version="1",
                input_hash="b" * 64,
                task_snapshot={},
                url_context=[{"url_id": str(url.id), "role": "changed"}],
                source_coverage={},
            )
        )
        db.flush()
        evaluation = evaluate_effect_cohort(
            db, website.id, change_date, change_date, as_of=date(2026, 9, 30)
        )

        assert "behavior_observation" in evaluation.metrics
        assert evaluation.evidence[0]["basis"] == "observed_correlation"

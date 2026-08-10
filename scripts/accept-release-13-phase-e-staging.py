#!/usr/bin/env python3
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
from app.services.sensor_aggregates import reconcile_sensor_measurement_state


def main() -> None:
    with SessionLocal() as db:
        client = Client(name="Release 13 phase E synthetic client")
        website = Website(
            client=client,
            name="Release 13 phase E synthetic site",
            base_url="https://sensor-phase-e.example.test",
        )
        db.add(website)
        db.flush()
        client_id = client.id
        try:
            url = Url(
                website_id=website.id,
                normalized_url="https://sensor-phase-e.example.test/offerte",
                current_status_code=200,
                is_active=True,
                is_indexable=True,
            )
            db.add(url)
            db.flush()
            db.add(
                SensorManifest(
                    website_id=website.id,
                    schema_version="1",
                    manifest_version="2026-08-10.1",
                    profile="lead_generation",
                    page_match="/offerte",
                    observations=[
                        {"key": "quote_form", "kind": "process", "locator": "quote-form"}
                    ],
                    content_hash="a" * 64,
                    status="active",
                    valid_from=datetime(2026, 6, 1, tzinfo=UTC),
                    expires_at=datetime(2026, 10, 1, tzinfo=UTC),
                )
            )
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
                        SensorDailyPageMetric(
                            website_id=website.id,
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
                            rejected_count=0,
                            sampled_count=0,
                        ),
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
                    description="Synthetic evidence",
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
                select(OpportunityEvaluation).where(
                    OpportunityEvaluation.website_id == website.id,
                    OpportunityEvaluation.scope_key.like("ctr:%"),
                )
            )
            assert opportunity is not None
            assert opportunity.source_coverage["behavior_observation"] is True

            task = RecommendationTask(
                website_id=website.id,
                recommendation_type="content_update",
                definition_version="1",
                title="Synthetic update",
                category="content",
                status="implemented",
                primary_role="content",
                supporting_roles=[],
                priority="normal",
                priority_reason="Synthetic test",
                feasibility="ready",
                action="Update",
                rationale="Synthetic test",
                steps=[],
                dependencies=[],
                required_input=[],
                acceptance_criteria=[],
                verification_spec={},
            )
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
            effect = evaluate_effect_cohort(
                db, website.id, change_date, change_date, as_of=date(2026, 9, 30)
            )
            assert "behavior_observation" in effect.metrics
            assert effect.evidence[0]["basis"] == "observed_correlation"
            print(
                {
                    "status": "release_13_phase_e_staging_ok",
                    "measurement_status": state.status,
                    "observed_pages": state.observed_pages,
                    "opportunity_enriched": True,
                    "effect_non_causal": True,
                }
            )
        finally:
            db.rollback()
            stored_client = db.get(Client, client.id)
            if stored_client is not None:
                db.delete(stored_client)
                db.commit()

    with SessionLocal() as db:
        assert db.get(Client, client_id) is None
    print("release-13-phase-e-fixture-clean")


if __name__ == "__main__":
    main()

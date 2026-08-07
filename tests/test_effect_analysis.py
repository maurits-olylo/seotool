from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.discovery import Url
from app.models.effects import EffectEvaluation, EffectIntervention
from app.models.integrations import GoogleAnalyticsMetric, SearchConsoleMetric
from app.models.recommendations import RecommendationTask
from app.models.website import Website, WebsiteSettings
from app.services.effect_analysis import evaluate_effect_cohort, refresh_due_effect_evaluations


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


def test_effect_cohort_is_versioned_deduplicated_and_non_causal() -> None:
    with SessionLocal() as db:
        website = Website(
            client=Client(name="Effect cohort client"),
            name="Effect cohort site",
            base_url="https://example.com",
            settings=WebsiteSettings(primary_analytics_source="ga4"),
        )
        db.add(website)
        db.flush()
        url = Url(website_id=website.id, normalized_url="https://example.com/page")
        db.add(url)
        db.flush()
        task = _task(website.id)
        db.add(task)
        db.flush()
        intervention = EffectIntervention(
            website_id=website.id,
            task_id=task.id,
            implemented_at=datetime(2026, 1, 15, tzinfo=UTC),
            intervention_version="1",
            input_hash="a" * 64,
            task_snapshot={},
            url_context=[{"url_id": str(url.id), "role": "changed"}],
            source_coverage={},
        )
        db.add(intervention)
        db.flush()
        for offset in range(28):
            for metric_date, clicks, impressions, sessions, conversions in (
                (date(2025, 12, 18) + timedelta(days=offset), 10, 100, 20, 2),
                (date(2026, 3, 4) + timedelta(days=offset), 20, 150, 30, 4),
            ):
                db.add_all(
                    [
                        SearchConsoleMetric(
                            website_id=website.id,
                            url_id=url.id,
                            date=metric_date,
                            page_url=url.normalized_url,
                            clicks=clicks,
                            impressions=impressions,
                            ctr=clicks / impressions,
                            position=5,
                        ),
                        GoogleAnalyticsMetric(
                            website_id=website.id,
                            url_id=url.id,
                            date=metric_date,
                            landing_page="/page",
                            sessions=sessions,
                            active_users=sessions - 2,
                            key_events=conversions,
                        ),
                    ]
                )
        db.flush()

        first = evaluate_effect_cohort(
            db, website.id, date(2026, 1, 15), date(2026, 1, 15), as_of=date(2026, 3, 31)
        )
        second = evaluate_effect_cohort(
            db, website.id, date(2026, 1, 15), date(2026, 1, 15), as_of=date(2026, 3, 31)
        )

        assert first is second
        assert db.query(EffectEvaluation).count() == 1
        assert first.status == "development_visible"
        assert first.analytics_source == "ga4"
        assert first.metrics["gsc"]["changes"]["clicks"]["relative_percent"] == 100.0
        assert first.evidence[0]["basis"] == "observed_correlation"


def test_effect_cohort_marks_recent_intervention_too_early() -> None:
    with SessionLocal() as db:
        website = Website(
            client=Client(name="Recent effect client"),
            name="Recent effect site",
            base_url="https://recent.example",
            settings=WebsiteSettings(),
        )
        db.add(website)
        db.flush()
        url = Url(website_id=website.id, normalized_url="https://recent.example/page")
        db.add(url)
        db.flush()
        task = _task(website.id)
        db.add(task)
        db.flush()
        db.add(
            EffectIntervention(
                website_id=website.id,
                task_id=task.id,
                implemented_at=datetime(2026, 3, 20, tzinfo=UTC),
                intervention_version="1",
                input_hash="b" * 64,
                task_snapshot={},
                url_context=[{"url_id": str(url.id), "role": "changed"}],
                source_coverage={},
            )
        )
        db.flush()

        evaluation = evaluate_effect_cohort(
            db, website.id, date(2026, 3, 20), date(2026, 3, 20), as_of=date(2026, 3, 31)
        )

        assert evaluation.status == "too_early"
        assert evaluation.confidence_factors["mature"] is False


def test_effect_cohort_is_refreshed_automatically_after_maturity() -> None:
    with SessionLocal() as db:
        website = Website(
            client=Client(name="Automatic effect client"),
            name="Automatic effect site",
            base_url="https://automatic-effect.example",
            settings=WebsiteSettings(),
        )
        db.add(website)
        db.flush()
        task = _task(website.id)
        db.add(task)
        db.flush()
        db.add(
            EffectIntervention(
                website_id=website.id,
                task_id=task.id,
                implemented_at=datetime(2026, 1, 1, tzinfo=UTC),
                intervention_version="1",
                input_hash="c" * 64,
                task_snapshot={},
                url_context=[],
                source_coverage={},
            )
        )
        db.flush()
        evaluate_effect_cohort(
            db, website.id, date(2026, 1, 1), date(2026, 1, 1), as_of=date(2026, 1, 10)
        )

        assert refresh_due_effect_evaluations(db, as_of=date(2026, 1, 20)) == 0
        assert refresh_due_effect_evaluations(db, as_of=date(2026, 2, 12)) == 1
        assert db.query(EffectEvaluation).count() == 2


def test_effect_evaluation_api_calculates_lists_and_validates(client: TestClient) -> None:
    with SessionLocal() as db:
        website = Website(
            client=Client(name="Effect API client"),
            name="Effect API site",
            base_url="https://effect-api.example",
            settings=WebsiteSettings(),
        )
        db.add(website)
        db.commit()
        website_id = website.id

    created = client.post(
        f"/api/v1/websites/{website_id}/effect-evaluations/evaluate",
        params={"change_period_start": "2026-01-01", "change_period_end": "2026-01-31"},
    )
    assert created.status_code == 200
    assert created.json()["status"] == "insufficient_data"
    assert "input_hash" not in created.json()

    listed = client.get(f"/api/v1/websites/{website_id}/effect-evaluations")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [created.json()["id"]]

    invalid = client.post(
        f"/api/v1/websites/{website_id}/effect-evaluations/evaluate",
        params={"change_period_start": "2026-02-01", "change_period_end": "2026-01-01"},
    )
    assert invalid.status_code == 422

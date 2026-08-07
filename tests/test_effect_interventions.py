from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.content_analysis import UrlContentClassification, UrlContentOverride
from app.models.discovery import Url
from app.models.effects import EffectIntervention
from app.models.recommendations import RecommendationTask, RecommendationTaskUrl
from app.models.website import Website, WebsiteSettings
from app.services.effect_interventions import materialize_task_intervention


def _task(db, *, status: str = "implemented"):  # type: ignore[no-untyped-def]
    website = Website(
        client=Client(name="Effect client"),
        name="Effect website",
        base_url="https://example.com",
        settings=WebsiteSettings(),
    )
    db.add(website)
    db.flush()
    url = Url(website_id=website.id, normalized_url="https://example.com/landing-page")
    db.add(url)
    db.flush()
    implemented_at = datetime.now(UTC)
    task = RecommendationTask(
        website_id=website.id,
        recommendation_type="improve_landing_page",
        definition_version="1",
        title="Verbeter landingspagina",
        category="content",
        status=status,
        primary_role="content",
        supporting_roles=[],
        priority="normal",
        priority_reason="De pagina heeft aantoonbare zoekvraag.",
        feasibility="ready",
        action="Werk de pagina bij.",
        rationale="Sluit beter aan op de zoekintentie.",
        steps=[],
        dependencies=[],
        required_input=[],
        acceptance_criteria=[],
        verification_spec={},
        implemented_at=implemented_at if status == "implemented" else None,
    )
    db.add(task)
    db.flush()
    return website, url, task, implemented_at


def test_materializes_versioned_task_scope_with_historical_context() -> None:
    with SessionLocal() as db:
        website, url, task, implemented_at = _task(db)
        classification = UrlContentClassification(
            website_id=website.id,
            url_id=url.id,
            period_start=None,
            period_end=None,
            input_hash="a" * 64,
            classification_version="1",
            search_intent="commercial",
            journey_stage="consideration",
            content_role="landing_page",
            confidence=0.8,
            probabilities={},
            source_coverage={"gsc_queries": True},
            evidence=[],
            created_at=implemented_at - timedelta(minutes=2),
            updated_at=implemented_at - timedelta(minutes=2),
        )
        override = UrlContentOverride(
            website_id=website.id,
            url_id=url.id,
            search_intent="transactional",
            is_locked=True,
            updated_at=implemented_at - timedelta(minutes=1),
        )
        db.add_all(
            [
                classification,
                override,
                RecommendationTaskUrl(task_id=task.id, url_id=url.id, role="changed"),
            ]
        )
        db.flush()

        first = materialize_task_intervention(db, task)
        second = materialize_task_intervention(db, task)

        assert first is not None
        assert second is first
        assert db.query(EffectIntervention).count() == 1
        assert first.task_snapshot["recommendation_type"] == "improve_landing_page"
        assert first.url_context[0]["classification_id"] == str(classification.id)
        assert first.url_context[0]["search_intent"] == "transactional"
        assert first.url_context[0]["journey_stage"] == "consideration"
        assert first.url_context[0]["override_id"] == str(override.id)
        assert first.source_coverage["classified_urls"] == 1
        assert first.source_coverage["total_urls"] == 1
        assert len(first.input_hash) == 64


def test_rejects_unimplemented_or_unscoped_task() -> None:
    with SessionLocal() as db:
        _website, url, open_task, _implemented_at = _task(db, status="open")
        db.add(RecommendationTaskUrl(task_id=open_task.id, url_id=url.id, role="changed"))
        db.flush()
        assert materialize_task_intervention(db, open_task) is None

    with SessionLocal() as db:
        _website, _url, implemented_task, _implemented_at = _task(db)
        assert materialize_task_intervention(db, implemented_task) is None


def test_effect_intervention_registration_api_is_explicit_and_idempotent(
    client: TestClient,
) -> None:
    with SessionLocal() as db:
        _website, url, task, _implemented_at = _task(db)
        db.add(RecommendationTaskUrl(task_id=task.id, url_id=url.id, role="changed"))
        db.commit()
        task_id = task.id

    first = client.post(f"/api/v1/recommendation-tasks/{task_id}/effect-intervention")
    second = client.post(f"/api/v1/recommendation-tasks/{task_id}/effect-intervention")

    assert first.status_code == 200
    assert first.json()["created"] is True
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["id"] == first.json()["id"]

    with SessionLocal() as db:
        _website, _url, unscoped_task, _implemented_at = _task(db)
        db.commit()
        unscoped_task_id = unscoped_task.id

    rejected = client.post(f"/api/v1/recommendation-tasks/{unscoped_task_id}/effect-intervention")
    assert rejected.status_code == 422

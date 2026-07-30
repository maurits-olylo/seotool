import pytest
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.discovery import Url
from app.models.issues import Issue
from app.models.recommendations import (
    RecommendationFeedback,
    RecommendationTask,
    RecommendationTaskEvent,
    RecommendationTaskIssue,
    RecommendationTaskUrl,
)
from app.models.website import Website, WebsiteSettings
from app.services.recommendation_library import (
    DEFINITIONS,
    get_recommendation_definition,
    recommendation_for_issue_type,
)


def _task_fixture(db):  # type: ignore[no-untyped-def]
    website = Website(
        client=Client(name="Recommendation client"),
        name="Recommendation website",
        base_url="https://example.com",
        settings=WebsiteSettings(),
    )
    db.add(website)
    db.flush()
    url = Url(website_id=website.id, normalized_url="https://example.com/source")
    issue = Issue(
        website_id=website.id,
        url_id=url.id,
        issue_type="internally_linked_404",
        category="internal_links",
        severity="high",
        title="Defecte link",
        description="Een interne link geeft 404.",
        recommended_action="Herstel de link.",
    )
    db.add_all([url, issue])
    db.flush()
    definition = get_recommendation_definition("repair_broken_internal_link")
    task = RecommendationTask(
        website_id=website.id,
        primary_issue_id=issue.id,
        recommendation_type=definition.key,
        definition_version=definition.version,
        title=definition.title,
        category="internal_links",
        primary_role=definition.primary_role,
        supporting_roles=list(definition.supporting_roles),
        priority=definition.default_priority,
        priority_reason="De link blokkeert bezoekers en crawlers.",
        effort_min_minutes=definition.effort_minutes[0] if definition.effort_minutes else None,
        effort_max_minutes=definition.effort_minutes[1] if definition.effort_minutes else None,
        feasibility=definition.feasibility,
        action="Vervang de defecte link.",
        rationale="Het doel is niet bereikbaar.",
        steps=list(definition.steps),
        acceptance_criteria=list(definition.completion_criteria),
        verification_spec={"scope": list(definition.verification_scope)},
    )
    db.add(task)
    db.flush()
    return website, url, issue, task


def test_library_contains_compact_unique_mvp() -> None:
    assert len(DEFINITIONS) == 15
    assert len({definition.key for definition in DEFINITIONS}) == 15
    assert recommendation_for_issue_type("internally_linked_404").key == (
        "repair_broken_internal_link"
    )
    assert recommendation_for_issue_type("thin_content") is None


def test_task_links_issues_urls_events_and_feedback() -> None:
    with SessionLocal() as db:
        website, url, issue, task = _task_fixture(db)
        db.add_all(
            [
                RecommendationTaskIssue(task_id=task.id, issue_id=issue.id),
                RecommendationTaskUrl(task_id=task.id, url_id=url.id, role="source"),
                RecommendationTaskEvent(
                    task_id=task.id,
                    actor_label="SEO specialist",
                    event_type="status_changed",
                    previous_status="open",
                    new_status="planned",
                ),
                RecommendationFeedback(
                    task_id=task.id,
                    actual_minutes=20,
                    actual_effort_band="15_30_minutes",
                    difficulty="easy",
                    instruction_helpful=True,
                    verification_outcome="passed",
                    final_assessment="verified",
                ),
            ]
        )
        db.commit()

        assert db.query(RecommendationTask).filter_by(website_id=website.id).count() == 1
        assert db.query(RecommendationTaskIssue).filter_by(task_id=task.id).count() == 1
        assert db.query(RecommendationTaskUrl).filter_by(task_id=task.id).count() == 1
        assert db.query(RecommendationTaskEvent).filter_by(task_id=task.id).count() == 1
        assert db.query(RecommendationFeedback).filter_by(task_id=task.id).count() == 1


def test_task_constraints_reject_invalid_status_and_effort() -> None:
    with SessionLocal() as db:
        _website, _url, _issue, task = _task_fixture(db)
        task.status = "verification_running"
        task.effort_min_minutes = 60
        task.effort_max_minutes = 30
        with pytest.raises(IntegrityError):
            db.commit()

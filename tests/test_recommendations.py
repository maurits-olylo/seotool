from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.client import Client
from app.models.discovery import Url
from app.models.issues import ActivityLog, Issue
from app.models.recommendations import (
    RecommendationFeedback,
    RecommendationTask,
    RecommendationTaskEvent,
    RecommendationTaskIssue,
    RecommendationTaskUrl,
)
from app.models.user import ClientMembership, User
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
                    actual_effort_band="15_30",
                    difficulty="easy",
                    instruction_helpful=True,
                    verification_outcome="passed",
                    final_assessment="completed",
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


def test_recommendation_task_api_lifecycle(client) -> None:  # type: ignore[no-untyped-def]
    customer = client.post("/api/v1/clients", json={"name": "Task API client"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Task API website",
            "base_url": "https://example.com",
        },
    ).json()
    with SessionLocal() as db:
        website_id = UUID(website["id"])
        url = Url(website_id=website_id, normalized_url="https://example.com/source")
        db.add(url)
        db.flush()
        issue = Issue(
            website_id=website_id,
            url_id=url.id,
            issue_type="internally_linked_404",
            category="internal_links",
            severity="high",
            title="Defecte interne link",
            description="De link geeft 404.",
            recommended_action="Vervang de link.",
        )
        db.add(issue)
        db.commit()
        issue_id = issue.id

    definitions = client.get("/api/v1/recommendation-types")
    assert definitions.status_code == 200
    assert len(definitions.json()) == 15

    created = client.post(f"/api/v1/issues/{issue_id}/recommendation-task")
    assert created.status_code == 201
    task = created.json()
    task_id = task["id"]
    assert task["recommendation_type"] == "repair_broken_internal_link"
    assert task["primary_role"] == "content"
    assert task["priority"] == "high"
    assert task["status"] == "open"
    assert task["verification_status"] == "not_requested"

    duplicate = client.post(f"/api/v1/issues/{issue_id}/recommendation-task")
    assert duplicate.status_code == 409

    tasks = client.get(f"/api/v1/websites/{website['id']}/recommendation-tasks")
    assert tasks.status_code == 200
    assert [item["id"] for item in tasks.json()] == [task_id]

    detail = client.get(f"/api/v1/recommendation-tasks/{task_id}")
    assert detail.status_code == 200
    assert detail.json()["issue_ids"] == [str(issue_id)]
    assert detail.json()["urls"][0]["role"] == "source"
    assert detail.json()["events"][0]["event_type"] == "created"

    planned = client.patch(
        f"/api/v1/recommendation-tasks/{task_id}",
        json={"status": "planned", "comment": "In de sprint opgenomen."},
    )
    assert planned.status_code == 200
    assert planned.json()["status"] == "planned"

    invalid_transition = client.patch(
        f"/api/v1/recommendation-tasks/{task_id}",
        json={"status": "implemented"},
    )
    assert invalid_transition.status_code == 422
    premature_feedback = client.post(
        f"/api/v1/recommendation-tasks/{task_id}/feedback",
        json={"actual_minutes": 30},
    )
    assert premature_feedback.status_code == 422

    in_progress = client.patch(
        f"/api/v1/recommendation-tasks/{task_id}",
        json={"status": "in_progress"},
    )
    assert in_progress.status_code == 200
    implemented = client.patch(
        f"/api/v1/recommendation-tasks/{task_id}",
        json={"status": "implemented"},
    )
    assert implemented.status_code == 200
    assert implemented.json()["implemented_at"] is not None
    feedback = client.post(
        f"/api/v1/recommendation-tasks/{task_id}/feedback",
        json={
            "actual_minutes": 35,
            "actual_effort_band": "30_60",
            "difficulty": "expected",
            "instruction_helpful": True,
            "missing_input": False,
            "missing_dependency": False,
            "final_assessment": "completed",
            "notes": "De stappen waren duidelijk.",
        },
    )
    assert feedback.status_code == 201
    assert feedback.json()["actual_minutes"] == 35
    assert feedback.json()["actual_effort_band"] == "30_60"
    with SessionLocal() as db:
        event = (
            db.query(RecommendationTaskEvent)
            .filter_by(task_id=UUID(task_id), event_type="feedback_recorded")
            .one()
        )
        activity = (
            db.query(ActivityLog)
            .filter_by(
                website_id=website_id,
                activity_type="recommendation_feedback_recorded",
            )
            .one()
        )
        assert event.details["actual_effort_band"] == "30_60"
        assert "notes" not in event.details
        assert "notes" not in activity.details
    recorded_feedback = client.get(
        f"/api/v1/recommendation-tasks/{task_id}/feedback"
    )
    assert recorded_feedback.status_code == 200
    assert [item["id"] for item in recorded_feedback.json()] == [feedback.json()["id"]]
    assert (
        client.post(f"/api/v1/recommendation-tasks/{task_id}/feedback", json={}).status_code
        == 422
    )

    missing_close_reason = client.patch(
        f"/api/v1/recommendation-tasks/{task_id}",
        json={"status": "closed"},
    )
    assert missing_close_reason.status_code == 422
    closed = client.patch(
        f"/api/v1/recommendation-tasks/{task_id}",
        json={"status": "closed", "close_reason": "verified"},
    )
    assert closed.status_code == 200
    assert closed.json()["close_reason"] == "verified"
    assert closed.json()["closed_at"] is not None
    assert (
        client.get(f"/api/v1/websites/{website['id']}/recommendation-tasks").json() == []
    )

    reopen_without_comment = client.patch(
        f"/api/v1/recommendation-tasks/{task_id}",
        json={"status": "open"},
    )
    assert reopen_without_comment.status_code == 422
    reopened = client.patch(
        f"/api/v1/recommendation-tasks/{task_id}",
        json={"status": "open", "comment": "Probleem kwam terug."},
    )
    assert reopened.status_code == 200
    assert reopened.json()["close_reason"] is None
    assert reopened.json()["closed_at"] is None


def test_client_role_can_read_but_not_change_recommendation_tasks(client) -> None:  # type: ignore[no-untyped-def]
    customer = client.post("/api/v1/clients", json={"name": "Read-only task client"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Read-only task website",
            "base_url": "https://readonly.example.com",
        },
    ).json()
    website_id = UUID(website["id"])
    with SessionLocal() as db:
        report_user = User(
            email="task-reader@example.com",
            role="client",
            password_hash=hash_password("task-reader-secure-password"),
        )
        db.add(report_user)
        db.flush()
        db.add(
            ClientMembership(
                user_id=report_user.id,
                client_id=UUID(customer["id"]),
                role="client",
            )
        )
        issue = Issue(
            website_id=website_id,
            issue_type="http_404",
            category="reachability",
            severity="high",
            title="Pagina geeft 404",
            description="De pagina is niet bereikbaar.",
            recommended_action="Herstel of redirect de pagina.",
        )
        db.add(issue)
        db.commit()
        issue_id = issue.id

    created = client.post(f"/api/v1/issues/{issue_id}/recommendation-task")
    assert created.status_code == 201
    task_id = created.json()["id"]

    from app.main import app

    browser = TestClient(app)
    assert (
        browser.post(
            "/ui/login",
            json={
                "email": "task-reader@example.com",
                "password": "task-reader-secure-password",
            },
        ).status_code
        == 204
    )
    assert (
        browser.get(f"/api/v1/websites/{website_id}/recommendation-tasks").status_code
        == 200
    )
    assert browser.get(f"/api/v1/recommendation-tasks/{task_id}").status_code == 200
    assert (
        browser.get(f"/api/v1/recommendation-tasks/{task_id}/feedback").status_code
        == 200
    )
    assert (
        browser.post(f"/api/v1/issues/{issue_id}/recommendation-task").status_code
        == 403
    )
    assert (
        browser.patch(
            f"/api/v1/recommendation-tasks/{task_id}",
            json={"status": "planned"},
        ).status_code
        == 403
    )
    assert (
        browser.post(
            f"/api/v1/recommendation-tasks/{task_id}/feedback",
            json={"actual_minutes": 20},
        ).status_code
        == 403
    )

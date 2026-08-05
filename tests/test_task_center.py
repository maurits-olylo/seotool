from uuid import UUID

from fastapi.testclient import TestClient

from app.core.security import create_session_token, hash_password
from app.db.session import SessionLocal
from app.models.client import Client
from app.models.issues import Issue
from app.models.recommendations import RecommendationTask, TaskNotificationReceipt
from app.models.user import ClientMembership, User
from app.models.website import Website, WebsiteSettings


def test_task_center_filters_and_user_specific_notification_receipts(client) -> None:  # type: ignore[no-untyped-def]
    with SessionLocal() as db:
        customer = Client(name="Task center")
        website = Website(
            client=customer,
            name="Task center website",
            base_url="https://example.com",
            settings=WebsiteSettings(),
        )
        user = User(
            email="task-center@example.com",
            password_hash=hash_password("task-center-secure-password"),
            role="user",
        )
        db.add_all([website, user])
        db.flush()
        db.add(ClientMembership(user_id=user.id, client_id=customer.id, role="admin"))
        issue = Issue(
            website_id=website.id,
            issue_type="missing_title",
            category="onpage",
            severity="medium",
            title="Title ontbreekt",
            description="De title ontbreekt.",
            recommended_action="Voeg een title toe.",
        )
        db.add(issue)
        db.commit()
        website_id = website.id
        user_id = user.id
        issue_id = issue.id

    created = client.post(f"/api/v1/issues/{issue_id}/recommendation-task")
    assert created.status_code == 201
    task_id = created.json()["id"]
    updated = client.patch(
        f"/api/v1/recommendation-tasks/{task_id}",
        json={
            "status": "planned",
            "assigned_to_user_id": str(user_id),
            "primary_role": "content_editor",
        },
    )
    assert updated.status_code == 200

    matching = client.get(
        f"/api/v1/websites/{website_id}/recommendation-tasks",
        params={
            "status": "planned",
            "primary_role": "content_editor",
            "priority": "normal",
            "assigned_to_user_id": str(user_id),
            "search": "title",
        },
    )
    assert matching.status_code == 200
    assert [item["id"] for item in matching.json()] == [task_id]
    unassigned_update = client.patch(
        f"/api/v1/recommendation-tasks/{task_id}",
        json={"assigned_to_user_id": None},
    )
    assert unassigned_update.status_code == 200
    assert unassigned_update.json()["assigned_to_user_id"] is None
    unassigned = client.get(
        f"/api/v1/websites/{website_id}/recommendation-tasks",
        params={"unassigned": True},
    )
    assert [item["id"] for item in unassigned.json()] == [task_id]
    assert (
        client.get(
            f"/api/v1/websites/{website_id}/recommendation-tasks",
            params={"primary_role": "ux_ui_design"},
        ).json()
        == []
    )

    notifications = client.get(f"/api/v1/websites/{website_id}/task-notifications")
    assert notifications.status_code == 200
    assert {item["notification_type"] for item in notifications.json()} == {
        "task_assigned",
        "task_status_changed",
    }
    notification_id = notifications.json()[0]["id"]
    assert client.post(f"/api/v1/task-notifications/{notification_id}/read").status_code == 403

    from app.main import app

    browser = TestClient(app)
    browser.cookies.set("seo_session", create_session_token(user_id))
    marked = browser.post(f"/api/v1/task-notifications/{notification_id}/read")
    assert marked.status_code == 204
    unread = browser.get(
        f"/api/v1/websites/{website_id}/task-notifications",
        params={"unread_only": True},
    )
    assert unread.status_code == 200
    assert notification_id not in {item["id"] for item in unread.json()}
    with SessionLocal() as db:
        assert db.get(TaskNotificationReceipt, (UUID(notification_id), user_id)) is not None
        task = db.get(RecommendationTask, UUID(task_id))
        assert task is not None and task.primary_role == "content_editor"
        assert task.assigned_to_user_id is None

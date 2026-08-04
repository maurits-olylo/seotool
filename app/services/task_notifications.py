from sqlalchemy.orm import Session

from app.models.recommendations import (
    RecommendationTask,
    RecommendationVerification,
    TaskNotification,
)


def add_task_notification(
    db: Session,
    *,
    task: RecommendationTask,
    notification_type: str,
    title: str,
    message: str,
    verification: RecommendationVerification | None = None,
    details: dict[str, object] | None = None,
) -> TaskNotification:
    notification = TaskNotification(
        website_id=task.website_id,
        task_id=task.id,
        verification_id=verification.id if verification else None,
        notification_type=notification_type,
        title=title,
        message=message,
        details=details or {},
    )
    db.add(notification)
    return notification

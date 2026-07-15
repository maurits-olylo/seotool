import time
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.common import utc_now
from app.models.discovery import CrawlJob
from app.models.system import CrawlDeploymentControl

STATUSES_TO_PAUSE = ("pending", "running")
UNSAFE_STATUSES = ("running", "pause_requested")


@dataclass(frozen=True)
class DeploymentDrainStatus:
    active: bool
    tracked_job_ids: tuple[str, ...]
    waiting_job_ids: tuple[str, ...]

    @property
    def safe(self) -> bool:
        return self.active and not self.waiting_job_ids


def _control(db: Session, *, lock: bool = False) -> CrawlDeploymentControl:
    query = select(CrawlDeploymentControl).where(CrawlDeploymentControl.id == 1)
    if lock:
        query = query.with_for_update()
    control = db.scalar(query)
    if control is None:
        control = CrawlDeploymentControl(id=1)
        db.add(control)
        db.flush()
    return control


def crawl_deployment_is_active(db: Session) -> bool:
    return bool(
        db.scalar(select(CrawlDeploymentControl.is_active).where(CrawlDeploymentControl.id == 1))
    )


def pause_job_if_deployment_active(db: Session, job: CrawlJob) -> bool:
    """Close the enqueue race between a crawl creator and a newly activated drain."""
    control = _control(db, lock=True)
    if not control.is_active:
        return False
    tracked = set(control.paused_job_ids)
    tracked.add(str(job.id))
    control.paused_job_ids = sorted(tracked)
    control.updated_at = utc_now()
    job.status = "paused"
    db.commit()
    return True


def start_deployment_drain(db: Session) -> DeploymentDrainStatus:
    control = _control(db, lock=True)
    if not control.is_active:
        control.is_active = True
        control.started_at = utc_now()
        control.paused_job_ids = []
        db.commit()

    control = _control(db, lock=True)
    tracked = set(control.paused_job_ids)
    jobs = list(db.scalars(select(CrawlJob).where(CrawlJob.status.in_(STATUSES_TO_PAUSE))))
    for job in jobs:
        job_id = str(job.id)
        if job_id in tracked:
            continue
        tracked.add(job_id)
        job.status = "paused" if job.status == "pending" else "pause_requested"
    control.paused_job_ids = sorted(tracked)
    control.updated_at = utc_now()
    db.commit()
    return deployment_drain_status(db)


def deployment_drain_status(db: Session) -> DeploymentDrainStatus:
    control = _control(db)
    tracked = tuple(control.paused_job_ids)
    waiting = [
        str(job_id)
        for job_id in db.scalars(select(CrawlJob.id).where(CrawlJob.status.in_(UNSAFE_STATUSES)))
    ]
    return DeploymentDrainStatus(bool(control.is_active), tracked, tuple(sorted(waiting)))


def wait_for_deployment_drain(
    session_factory, *, timeout_seconds: float, poll_seconds: float = 1.0
) -> DeploymentDrainStatus:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout_seconds
    while True:
        with session_factory() as db:
            status = deployment_drain_status(db)
        if status.safe or not status.active:
            return status
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Crawls niet tijdig gepauzeerd: {', '.join(status.waiting_job_ids)}"
            )
        time.sleep(poll_seconds)


def finish_deployment_drain(db: Session) -> list[tuple[str, int]]:
    control = _control(db, lock=True)
    if not control.is_active:
        return []
    tracked = set(control.paused_job_ids)
    job_ids = [UUID(job_id) for job_id in tracked]
    jobs = list(db.scalars(select(CrawlJob).where(CrawlJob.id.in_(job_ids)))) if job_ids else []
    waiting = [
        str(job_id)
        for job_id in db.scalars(select(CrawlJob.id).where(CrawlJob.status.in_(UNSAFE_STATUSES)))
    ]
    if waiting:
        raise RuntimeError(f"Crawls zijn nog niet veilig gepauzeerd: {', '.join(waiting)}")
    resumed: list[tuple[str, int]] = []
    for job in jobs:
        if job.status == "paused":
            job.status = "pending"
            job.finished_at = None
            job.error_message = None
            resumed.append((str(job.id), job.attempt_count + 1))
    control.is_active = False
    control.paused_job_ids = []
    control.updated_at = utc_now()
    db.commit()
    return resumed

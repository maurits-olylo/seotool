import time
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.queue import enqueue_recommendation_verification
from app.core.security import Principal
from app.db.session import SessionLocal
from app.models.common import utc_now
from app.models.crawl import CrawlRun, UrlLink, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.issues import ActivityLog
from app.models.recommendations import (
    RecommendationTask,
    RecommendationTaskEvent,
    RecommendationTaskUrl,
    RecommendationVerification,
)
from app.models.website import Website
from app.services.http_crawler import CrawlError, fetch_url
from app.services.recommendation_library import get_recommendation_definition
from app.services.recommendation_tasks import (
    RecommendationTaskError,
    actor_label,
    verification_scope_plan,
)
from app.services.robots import RobotsRules
from app.services.snapshot import store_fetch_result
from app.services.url_normalization import NormalizationOptions, normalize_url

logger = structlog.get_logger()
ACTIVE_STATUSES = {"queued", "running"}
STATUS_FOR_OUTCOME = {
    "resolved": "passed",
    "probably_resolved": "likely_passed",
    "partially_resolved": "manual_review",
    "not_resolved": "failed",
    "manual_review_required": "manual_review",
}


def request_verification(
    db: Session,
    *,
    task: RecommendationTask,
    principal: Principal,
) -> RecommendationVerification:
    plan = verification_scope_plan(db, task=task)
    if not plan["can_request"]:
        raise RecommendationTaskError(str(plan["blocking_reason"]))
    existing = db.scalar(
        select(RecommendationVerification).where(
            RecommendationVerification.task_id == task.id,
            RecommendationVerification.status.in_(ACTIVE_STATUSES),
        )
    )
    if existing:
        raise RecommendationTaskError("Voor deze taak loopt al een verificatie.")

    task_urls = list(
        db.scalars(
            select(RecommendationTaskUrl).where(RecommendationTaskUrl.task_id == task.id)
        )
    )
    urls = {
        item.id: item
        for item in db.scalars(
            select(Url).where(Url.id.in_({item.url_id for item in task_urls}))
        )
    }
    scope_urls = [
        {
            "task_url_id": str(item.id),
            "url_id": str(item.url_id),
            "role": item.role,
            "url": urls[item.url_id].normalized_url,
        }
        for item in task_urls
    ]
    before_ids = _latest_snapshot_ids(db, {item.url_id for item in task_urls})
    job = CrawlJob(
        website_id=task.website_id,
        job_type="recommendation_verification",
        settings_snapshot={"verification_scope": scope_urls},
    )
    db.add(job)
    db.flush()
    verification = RecommendationVerification(
        task_id=task.id,
        requested_by_user_id=principal.user_id,
        crawl_job_id=job.id,
        verification_type=task.recommendation_type,
        scope_version=get_recommendation_definition(task.recommendation_type).version,
        scope={"urls": scope_urls},
        before_snapshot_ids=before_ids,
    )
    db.add(verification)
    task.verification_status = "queued"
    label = actor_label(db, principal)
    db.add_all(
        [
            RecommendationTaskEvent(
                task_id=task.id,
                actor_user_id=principal.user_id,
                actor_label=label,
                event_type="verification_queued",
                details={"crawl_job_id": str(job.id)},
            ),
            ActivityLog(
                website_id=task.website_id,
                actor=label,
                activity_type="recommendation_verification_queued",
                summary=f"Gerichte verificatie ingepland: {task.title}",
                details={"task_id": str(task.id), "crawl_job_id": str(job.id)},
            ),
        ]
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise RecommendationTaskError("Voor deze taak loopt al een verificatie.") from exc
    db.refresh(verification)
    try:
        enqueue_recommendation_verification(str(verification.id))
    except Exception:
        verification.status = "error"
        verification.error_message = "De verificatie kon niet aan de wachtrij worden toegevoegd."
        verification.finished_at = utc_now()
        task.verification_status = "error"
        db.commit()
        raise
    return verification


def execute_verification(verification_id: str) -> None:
    with SessionLocal() as db:
        verification = db.get(RecommendationVerification, uuid.UUID(verification_id))
        if verification is None or verification.status not in ACTIVE_STATUSES:
            return
        task = db.get(RecommendationTask, verification.task_id)
        job = db.get(CrawlJob, verification.crawl_job_id)
        if task is None or job is None:
            _fail(db, verification, task, job, "Taak of crawltaak bestaat niet meer.")
            return
        run = db.scalar(select(CrawlRun).where(CrawlRun.crawl_job_id == job.id))
        if run and run.status == "succeeded":
            return
        run = run or CrawlRun(
            crawl_job_id=job.id,
            website_id=job.website_id,
            crawl_type="recommendation_verification",
        )
        verification.status = task.verification_status = "running"
        verification.started_at = verification.started_at or utc_now()
        job.status = "running"
        job.started_at = job.started_at or utc_now()
        job.attempt_count += 1
        run.status = "running"
        run.phase = "targeted_verification"
        scope = list(verification.scope.get("urls", []))
        run.discovered_urls = len(scope)
        run.phase_total = len(scope)
        db.add(run)
        db.commit()
        try:
            website = db.get(Website, task.website_id)
            if website is None:
                raise RuntimeError("Website bestaat niet meer.")
            from app.jobs import _load_robots_rules

            robots = _load_robots_rules(db, job)
            roles = _roles(db, scope)
            fetch_urls = _fetch_urls(task.recommendation_type, roles)
            fetched_ids: set[uuid.UUID] = set(
                db.scalars(
                    select(UrlSnapshot.url_id).where(UrlSnapshot.crawl_run_id == run.id)
                )
            )
            for url in fetch_urls:
                if url.id in fetched_ids:
                    continue
                _fetch_scoped_url(db, website, run, url, robots=robots)
                fetched_ids.add(url.id)
                run.phase_current += 1
                run.heartbeat_at = utc_now()
                db.commit()
                if website.settings.request_delay_ms:
                    time.sleep(website.settings.request_delay_ms / 1000)
            rules = _evaluate(db, task.recommendation_type, roles, run.id)
            outcome = _outcome(rules)
            verification.rules = rules
            verification.result = {
                "outcome": outcome,
                "checked_url_ids": [
                    str(item)
                    for item in db.scalars(
                        select(UrlSnapshot.url_id).where(
                            UrlSnapshot.crawl_run_id == run.id
                        )
                    )
                ],
                "rule_counts": {
                    state: sum(rule["status"] == state for rule in rules)
                    for state in ("passed", "failed", "error")
                },
            }
            verification.after_snapshot_ids = [
                str(item)
                for item in db.scalars(
                    select(UrlSnapshot.id).where(UrlSnapshot.crawl_run_id == run.id)
                )
            ]
            verification.status = STATUS_FOR_OUTCOME[outcome]
            task.verification_status = verification.status
            run.status = job.status = (
                "succeeded"
                if outcome in {"resolved", "probably_resolved"}
                else "partially_succeeded"
            )
            _finish(db, verification, job, run)
        except Exception as exc:
            db.rollback()
            verification = db.get(RecommendationVerification, uuid.UUID(verification_id))
            task = db.get(RecommendationTask, verification.task_id) if verification else None
            job = db.get(CrawlJob, verification.crawl_job_id) if verification else None
            if verification and job and job.attempt_count < 3:
                verification.status = "queued"
                verification.error_message = str(exc)[:4000]
                if task:
                    task.verification_status = "queued"
                job.status = "pending"
                job.error_message = str(exc)[:4000]
                db.commit()
            else:
                _fail(db, verification, task, job, str(exc))
            logger.exception("recommendation_verification_failed", verification_id=verification_id)
            raise


def _fetch_scoped_url(
    db: Session,
    website: Website,
    run: CrawlRun,
    url: Url,
    *,
    robots: RobotsRules | None,
) -> None:
    settings = website.settings
    if robots and not robots.allows(url.normalized_url):
        db.add(
            UrlSnapshot(
                url_id=url.id,
                crawl_run_id=run.id,
                requested_url=url.normalized_url,
                error_message="Blocked by robots.txt",
                is_indexable=False,
            )
        )
        run.skipped_urls += 1
        return
    try:
        result = fetch_url(
            url.normalized_url,
            timeout_seconds=settings.request_timeout_seconds,
            max_response_size=settings.max_response_size,
        )
        store_fetch_result(db, url=url, crawl_run_id=run.id, result=result)
        run.crawled_urls += 1
    except CrawlError as exc:
        db.add(
            UrlSnapshot(
                url_id=url.id,
                crawl_run_id=run.id,
                requested_url=url.normalized_url,
                error_message=str(exc),
                is_indexable=False,
            )
        )
        run.failed_urls += 1


def _roles(db: Session, scope: list[object]) -> dict[str, list[Url]]:
    result: dict[str, list[Url]] = {}
    for item in scope:
        if not isinstance(item, dict):
            continue
        url = db.get(Url, uuid.UUID(str(item["url_id"])))
        if url:
            result.setdefault(str(item["role"]), []).append(url)
    return result


def _fetch_urls(verification_type: str, roles: dict[str, list[Url]]) -> list[Url]:
    requested = list(roles["source"])
    optional = {
        "repair_broken_internal_link": "replacement_target",
        "fix_redirect_chain_or_loop": "expected_target",
        "correct_canonical": "expected_canonical",
    }[verification_type]
    if optional in roles:
        requested.extend(roles[optional])
    return list({url.id: url for url in requested}.values())


def _evaluate(
    db: Session,
    verification_type: str,
    roles: dict[str, list[Url]],
    run_id: uuid.UUID,
) -> list[dict[str, object]]:
    snapshots = {
        item.url_id: item
        for item in db.scalars(
            select(UrlSnapshot).where(UrlSnapshot.crawl_run_id == run_id)
        )
    }
    source_urls = roles["source"]
    source_snapshots = [snapshots.get(item.id) for item in source_urls]
    source = source_snapshots[0]
    rules = [
        _status_rule(
            f"source_reachable:{url.id}",
            snapshots.get(url.id),
            expected_url=None,
        )
        for url in source_urls
    ]
    if verification_type == "repair_broken_internal_link":
        for broken_url in roles["broken_target"]:
            broken = broken_url.normalized_url
            still_linked = bool(
                db.scalar(
                    select(UrlLink.id).where(
                        UrlLink.crawl_run_id == run_id,
                        UrlLink.source_url_id.in_([item.id for item in source_urls]),
                        UrlLink.target_url == broken,
                    )
                )
            )
            rules.append(
                {
                    "rule": f"broken_target_not_linked:{broken_url.id}",
                    "status": (
                        "failed"
                        if still_linked
                        else (
                            "passed"
                            if all(
                                item and item.status_code == 200
                                for item in source_snapshots
                            )
                            else "error"
                        )
                    ),
                    "evidence": {"broken_target": broken, "still_linked": still_linked},
                }
            )
        if "replacement_target" in roles:
            rules.extend(
                _status_rule(
                    f"replacement_target_reachable:{url.id}",
                    snapshots.get(url.id),
                    expected_url=None,
                )
                for url in roles["replacement_target"]
            )
    elif verification_type == "fix_redirect_chain_or_loop":
        expected_url = roles["expected_target"][0]
        expected = expected_url.normalized_url
        rules.extend(
            [
                {
                    "rule": "redirect_chain_direct",
                    "status": (
                        "passed"
                        if source and len(source.redirect_chain) <= 1
                        else ("failed" if source else "error")
                    ),
                    "evidence": {"redirect_chain": source.redirect_chain if source else []},
                },
                _status_rule("expected_target_reached", source, expected_url=expected),
                _status_rule(
                    "expected_target_reachable",
                    snapshots.get(expected_url.id),
                    expected_url=None,
                ),
            ]
        )
    else:
        expected_url = roles["expected_canonical"][0]
        expected = expected_url.normalized_url
        canonical = _normalized(source.canonical, source_urls[0]) if source else None
        rules.extend(
            [
                {
                    "rule": "single_expected_canonical",
                    "status": (
                        "passed"
                        if canonical == expected
                        else ("failed" if source else "error")
                    ),
                    "evidence": {"canonical": canonical, "expected_canonical": expected},
                },
                _status_rule(
                    "expected_canonical_reachable",
                    snapshots.get(expected_url.id),
                    expected_url=None,
                ),
            ]
        )
    return rules


def _status_rule(
    name: str, snapshot: UrlSnapshot | None, *, expected_url: str | None
) -> dict[str, object]:
    if snapshot is None or snapshot.error_message:
        status = "error"
    elif snapshot.status_code != 200:
        status = "failed"
    elif expected_url and _normalized(snapshot.final_url, None) != expected_url:
        status = "failed"
    else:
        status = "passed"
    return {
        "rule": name,
        "status": status,
        "evidence": {
            "status_code": snapshot.status_code if snapshot else None,
            "final_url": snapshot.final_url if snapshot else None,
            "expected_url": expected_url,
            "error": snapshot.error_message if snapshot else "Geen snapshot",
        },
    }


def _normalized(value: str | None, fallback: Url | None) -> str | None:
    if not value:
        return fallback.normalized_url if fallback else None
    try:
        return normalize_url(value, options=NormalizationOptions())
    except ValueError:
        return value


def _outcome(rules: list[dict[str, object]]) -> str:
    states = [rule["status"] for rule in rules]
    if states and all(state == "passed" for state in states):
        return "resolved"
    if all(state == "error" for state in states):
        return "manual_review_required"
    if "passed" in states:
        return "partially_resolved"
    return "not_resolved"


def _latest_snapshot_ids(db: Session, url_ids: set[uuid.UUID]) -> list[str]:
    result: list[str] = []
    for url_id in url_ids:
        snapshot_id = db.scalar(
            select(UrlSnapshot.id)
            .where(UrlSnapshot.url_id == url_id)
            .order_by(UrlSnapshot.checked_at.desc())
            .limit(1)
        )
        if snapshot_id:
            result.append(str(snapshot_id))
    return result


def _finish(
    db: Session,
    verification: RecommendationVerification,
    job: CrawlJob,
    run: CrawlRun,
) -> None:
    finished = datetime.now(UTC)
    verification.finished_at = job.finished_at = run.finished_at = finished
    db.add(
        RecommendationTaskEvent(
            task_id=verification.task_id,
            event_type="verification_finished",
            details={
                "verification_id": str(verification.id),
                "outcome": verification.result.get("outcome"),
            },
        )
    )
    db.commit()


def _fail(
    db: Session,
    verification: RecommendationVerification | None,
    task: RecommendationTask | None,
    job: CrawlJob | None,
    message: str,
) -> None:
    if verification is None:
        return
    verification.status = "error"
    verification.error_message = message[:4000]
    verification.finished_at = utc_now()
    if task:
        task.verification_status = "error"
    if job:
        job.status = "failed"
        job.error_message = message[:4000]
        job.finished_at = utc_now()
        run = db.scalar(select(CrawlRun).where(CrawlRun.crawl_job_id == job.id))
        if run:
            run.status = "failed"
            run.finished_at = utc_now()
    db.commit()

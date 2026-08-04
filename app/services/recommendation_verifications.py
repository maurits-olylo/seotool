import time
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.queue import (
    VERIFICATION_QUEUE,
    enqueue_recommendation_verification,
    queue_has_capacity,
)
from app.core.security import Principal
from app.db.session import SessionLocal
from app.models.common import utc_now
from app.models.crawl import CrawlRun, UrlLink, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.issues import ActivityLog, Issue
from app.models.recommendations import (
    RecommendationTask,
    RecommendationTaskEvent,
    RecommendationTaskUrl,
    RecommendationVerification,
)
from app.models.website import Website
from app.services.html_extraction import INVALID_JSON_LD_MARKER
from app.services.http_crawler import CrawlError, fetch_url
from app.services.recommendation_library import get_recommendation_definition
from app.services.recommendation_tasks import (
    RecommendationTaskError,
    actor_label,
    verification_scope_plan,
)
from app.services.robots import RobotsRules
from app.services.snapshot import store_fetch_result
from app.services.task_notifications import add_task_notification
from app.services.technical_checks import _robots_conflict
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
    if get_settings().app_env != "test" and not queue_has_capacity(VERIFICATION_QUEUE):
        raise RecommendationTaskError("De verificatiewachtrij is tijdelijk vol.")

    task_urls = list(
        db.scalars(select(RecommendationTaskUrl).where(RecommendationTaskUrl.task_id == task.id))
    )
    urls = {
        item.id: item
        for item in db.scalars(select(Url).where(Url.id.in_({item.url_id for item in task_urls})))
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
    website = db.get(Website, task.website_id)
    priority = website.settings.queue_priority if website and website.settings else 50
    job = CrawlJob(
        website_id=task.website_id,
        job_type="recommendation_verification",
        settings_snapshot={"verification_scope": scope_urls},
        queue_name=VERIFICATION_QUEUE,
        queue_priority=priority,
    )
    db.add(job)
    db.flush()
    primary_issue = db.get(Issue, task.primary_issue_id) if task.primary_issue_id else None
    verification = RecommendationVerification(
        task_id=task.id,
        requested_by_user_id=principal.user_id,
        crawl_job_id=job.id,
        verification_type=task.recommendation_type,
        scope_version=get_recommendation_definition(task.recommendation_type).version,
        scope={
            "urls": scope_urls,
            "issue_type": primary_issue.issue_type if primary_issue else None,
        },
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
        queued = enqueue_recommendation_verification(
            str(verification.id),
            website_id=str(task.website_id),
            priority=priority,
        )
        if queued is False:
            raise RuntimeError("De verificatiewachtrij is tijdelijk vol.")
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
                db.scalars(select(UrlSnapshot.url_id).where(UrlSnapshot.crawl_run_id == run.id))
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
            rules = _evaluate(
                db,
                task.recommendation_type,
                roles,
                run.id,
                issue_type=(
                    str(verification.scope["issue_type"])
                    if verification.scope.get("issue_type")
                    else None
                ),
            )
            outcome = _outcome(rules)
            verification.rules = rules
            verification.result = {
                "outcome": outcome,
                "checked_url_ids": [
                    str(item)
                    for item in db.scalars(
                        select(UrlSnapshot.url_id).where(UrlSnapshot.crawl_run_id == run.id)
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
    primary_role = {
        "restore_or_redirect_missing_page": "old",
        "correct_indexability": "changed",
        "add_or_correct_title": "changed",
        "add_primary_heading": "changed",
        "add_meta_description": "changed",
        "repair_structured_data": "changed",
    }.get(verification_type, "source")
    requested = list(roles[primary_role])
    optional = {
        "repair_broken_internal_link": "replacement_target",
        "replace_redirected_internal_link": "expected_target",
        "restore_or_redirect_missing_page": "new",
        "fix_redirect_chain_or_loop": "expected_target",
        "correct_indexability": None,
        "correct_canonical": "expected_canonical",
        "add_or_correct_title": "sample",
        "add_primary_heading": "sample",
        "add_meta_description": "sample",
        "repair_structured_data": "sample",
    }[verification_type]
    if optional and optional in roles:
        requested.extend(roles[optional])
    return list({url.id: url for url in requested}.values())


def _evaluate(
    db: Session,
    verification_type: str,
    roles: dict[str, list[Url]],
    run_id: uuid.UUID,
    *,
    issue_type: str | None = None,
) -> list[dict[str, object]]:
    snapshots = {
        item.url_id: item
        for item in db.scalars(select(UrlSnapshot).where(UrlSnapshot.crawl_run_id == run_id))
    }
    primary_role = {
        "restore_or_redirect_missing_page": "old",
        "correct_indexability": "changed",
        "add_or_correct_title": "changed",
        "add_primary_heading": "changed",
        "add_meta_description": "changed",
        "repair_structured_data": "changed",
    }.get(verification_type, "source")
    source_urls = roles[primary_role]
    source_snapshots = [snapshots.get(item.id) for item in source_urls]
    source = source_snapshots[0]
    rules = [
        _status_rule(
            f"{primary_role}_reachable:{url.id}",
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
                            if all(item and item.status_code == 200 for item in source_snapshots)
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
    elif verification_type == "replace_redirected_internal_link":
        for redirected in roles["target"]:
            still_linked = bool(
                db.scalar(
                    select(UrlLink.id).where(
                        UrlLink.crawl_run_id == run_id,
                        UrlLink.source_url_id.in_([item.id for item in source_urls]),
                        UrlLink.target_url == redirected.normalized_url,
                    )
                )
            )
            rules.append(
                {
                    "rule": f"redirect_target_not_linked:{redirected.id}",
                    "status": (
                        "failed"
                        if still_linked
                        else (
                            "passed"
                            if all(item and item.status_code == 200 for item in source_snapshots)
                            else "error"
                        )
                    ),
                    "evidence": {
                        "redirect_target": redirected.normalized_url,
                        "still_linked": still_linked,
                    },
                }
            )
        if "expected_target" in roles:
            rules.extend(
                _status_rule(
                    f"expected_target_reachable:{url.id}",
                    snapshots.get(url.id),
                    expected_url=None,
                )
                for url in roles["expected_target"]
            )
    elif verification_type == "restore_or_redirect_missing_page":
        old_snapshot = source
        new_url = roles.get("new", [None])[0]
        new_snapshot = snapshots.get(new_url.id) if new_url else None
        restored = bool(old_snapshot and old_snapshot.status_code == 200)
        redirected = bool(
            old_snapshot
            and new_url
            and _normalized(old_snapshot.final_url, None) == new_url.normalized_url
            and new_snapshot
            and new_snapshot.status_code == 200
        )
        rules.append(
            {
                "rule": "old_url_restored_or_redirected",
                "status": (
                    "passed"
                    if restored or redirected
                    else ("error" if old_snapshot is None else "failed")
                ),
                "evidence": {
                    "old_status_code": old_snapshot.status_code if old_snapshot else None,
                    "old_final_url": old_snapshot.final_url if old_snapshot else None,
                    "replacement_url": new_url.normalized_url if new_url else None,
                    "replacement_status_code": (new_snapshot.status_code if new_snapshot else None),
                },
            }
        )
    elif verification_type == "correct_indexability":
        robots_values = {
            value.strip().lower()
            for value in (
                source.meta_robots if source else None,
                source.x_robots_tag if source else None,
            )
            if value
        }
        blocked = bool(source and source.error_message == "Blocked by robots.txt")
        rules.extend(
            [
                {
                    "rule": "robots_instructions_consistent",
                    "status": (
                        "failed"
                        if _robots_conflict(robots_values) or blocked
                        else ("passed" if source else "error")
                    ),
                    "evidence": {
                        "meta_robots": source.meta_robots if source else None,
                        "x_robots_tag": source.x_robots_tag if source else None,
                        "robots_txt_blocked": blocked,
                    },
                },
                {
                    "rule": "page_indexable",
                    "status": (
                        "passed"
                        if source and source.status_code == 200 and source.is_indexable
                        else ("error" if source is None else "failed")
                    ),
                    "evidence": {
                        "status_code": source.status_code if source else None,
                        "is_indexable": source.is_indexable if source else None,
                    },
                },
            ]
        )
    elif verification_type == "fix_redirect_chain_or_loop":
        expected_url = roles["expected_target"][0]
        expected = expected_url.normalized_url
        expected_snapshot = snapshots.get(expected_url.id)
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
                    expected_snapshot,
                    expected_url=None,
                ),
                _indexable_canonical_rule(
                    "expected_target_indexable_canonical",
                    expected_snapshot,
                    expected_url=expected,
                ),
            ]
        )
    elif verification_type == "correct_canonical":
        expected_url = roles["expected_canonical"][0]
        expected = expected_url.normalized_url
        expected_snapshot = snapshots.get(expected_url.id)
        canonical = _normalized(source.canonical, source_urls[0]) if source else None
        rules.extend(
            [
                {
                    "rule": "single_expected_canonical",
                    "status": (
                        "passed" if canonical == expected else ("failed" if source else "error")
                    ),
                    "evidence": {"canonical": canonical, "expected_canonical": expected},
                },
                _status_rule(
                    "expected_canonical_reachable",
                    expected_snapshot,
                    expected_url=None,
                ),
                _indexable_canonical_rule(
                    "expected_canonical_indexable",
                    expected_snapshot,
                    expected_url=expected,
                ),
            ]
        )
    elif verification_type == "add_or_correct_title":
        changed_snapshots = [snapshots.get(url.id) for url in roles["changed"]]
        compared = [
            item
            for item in [
                *changed_snapshots,
                *(snapshots.get(url.id) for url in roles.get("sample", [])),
            ]
            if item and item.status_code == 200 and item.title
        ]
        normalized_titles = [item.title.strip().casefold() for item in compared if item.title]
        rules.extend(
            [
                _field_present_rule("title_present", snapshot, "title")
                for snapshot in changed_snapshots
            ]
        )
        rules.append(
            {
                "rule": "title_unique_in_scope",
                "status": (
                    "passed"
                    if normalized_titles and len(normalized_titles) == len(set(normalized_titles))
                    else "failed"
                ),
                "evidence": {"compared_titles": normalized_titles},
            }
        )
    elif verification_type == "add_primary_heading":
        for url in roles["changed"]:
            snapshot = snapshots.get(url.id)
            h1_values = (snapshot.headings or {}).get("h1", []) if snapshot else []
            rules.append(
                {
                    "rule": f"single_primary_heading:{url.id}",
                    "status": (
                        "passed"
                        if len(h1_values) == 1 and h1_values[0].strip()
                        else ("error" if snapshot is None else "failed")
                    ),
                    "evidence": {"h1_values": h1_values},
                }
            )
    elif verification_type == "add_meta_description":
        changed_snapshots = [snapshots.get(url.id) for url in roles["changed"]]
        compared = [
            item
            for item in [
                *changed_snapshots,
                *(snapshots.get(url.id) for url in roles.get("sample", [])),
            ]
            if item and item.status_code == 200 and item.meta_description
        ]
        normalized_descriptions = [
            item.meta_description.strip().casefold() for item in compared if item.meta_description
        ]
        rules.extend(
            [
                _field_present_rule(
                    "meta_description_present",
                    snapshot,
                    "meta_description",
                )
                for snapshot in changed_snapshots
            ]
        )
        rules.append(
            {
                "rule": "meta_description_unique_in_scope",
                "status": (
                    "passed"
                    if normalized_descriptions
                    and len(normalized_descriptions) == len(set(normalized_descriptions))
                    else "failed"
                ),
                "evidence": {"compared_descriptions": normalized_descriptions},
            }
        )
    elif verification_type == "repair_structured_data":
        for url in roles["changed"]:
            snapshot = snapshots.get(url.id)
            invalid_blocks = (
                sum(
                    isinstance(value, dict) and value.get(INVALID_JSON_LD_MARKER) is True
                    for value in (snapshot.schema_data or [])
                )
                if snapshot
                else 0
            )
            breadcrumb_required = issue_type == "missing_breadcrumb_schema"
            intended_present = bool(
                snapshot
                and (
                    "BreadcrumbList" in (snapshot.schema_types or [])
                    if breadcrumb_required
                    else snapshot.schema_data
                )
            )
            rules.append(
                {
                    "rule": f"structured_data_valid:{url.id}",
                    "status": (
                        "passed"
                        if snapshot
                        and snapshot.status_code == 200
                        and invalid_blocks == 0
                        and intended_present
                        else ("error" if snapshot is None else "failed")
                    ),
                    "evidence": {
                        "invalid_json_ld_blocks": invalid_blocks,
                        "schema_types": snapshot.schema_types if snapshot else [],
                        "required_type": ("BreadcrumbList" if breadcrumb_required else None),
                    },
                }
            )
    else:
        raise ValueError(f"Unsupported verification type: {verification_type}")
    return rules


def _field_present_rule(
    name: str,
    snapshot: UrlSnapshot | None,
    field_name: str,
) -> dict[str, object]:
    value = getattr(snapshot, field_name, None) if snapshot else None
    return {
        "rule": name,
        "status": (
            "passed"
            if snapshot and snapshot.status_code == 200 and value and value.strip()
            else ("error" if snapshot is None else "failed")
        ),
        "evidence": {field_name: value},
    }


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


def _indexable_canonical_rule(
    name: str,
    snapshot: UrlSnapshot | None,
    *,
    expected_url: str,
) -> dict[str, object]:
    canonical = _normalized(snapshot.canonical, None) if snapshot else None
    canonical_matches = canonical in {None, expected_url}
    if snapshot is None or snapshot.error_message:
        status = "error"
    elif snapshot.status_code == 200 and snapshot.is_indexable and canonical_matches:
        status = "passed"
    else:
        status = "failed"
    return {
        "rule": name,
        "status": status,
        "evidence": {
            "status_code": snapshot.status_code if snapshot else None,
            "is_indexable": snapshot.is_indexable if snapshot else None,
            "canonical": canonical,
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
    task = db.get(RecommendationTask, verification.task_id)
    if task is not None:
        outcome = str(verification.result.get("outcome") or verification.status)
        add_task_notification(
            db,
            task=task,
            verification=verification,
            notification_type="verification_finished",
            title=f"Controle afgerond: {task.title}",
            message=f"De gerichte controle eindigde met uitkomst {outcome}.",
            details={"outcome": outcome, "status": verification.status},
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
        add_task_notification(
            db,
            task=task,
            verification=verification,
            notification_type="verification_failed",
            title=f"Controle mislukt: {task.title}",
            message="De gerichte controle kon niet worden afgerond.",
            details={"status": "error"},
        )
    if job:
        job.status = "failed"
        job.error_message = message[:4000]
        job.finished_at = utc_now()
        run = db.scalar(select(CrawlRun).where(CrawlRun.crawl_job_id == job.id))
        if run:
            run.status = "failed"
            run.finished_at = utc_now()
    db.commit()

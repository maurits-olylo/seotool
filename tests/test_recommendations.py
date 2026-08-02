from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.issues import ActivityLog, Issue, IssueOccurrence
from app.models.recommendations import (
    RecommendationFeedback,
    RecommendationTask,
    RecommendationTaskEvent,
    RecommendationTaskIssue,
    RecommendationTaskUrl,
    RecommendationVerification,
)
from app.models.user import ClientMembership, User
from app.models.website import Website, WebsiteSettings
from app.services.http_crawler import FetchResult
from app.services.recommendation_library import (
    DEFINITIONS,
    get_recommendation_definition,
    recommendation_for_issue_type,
)
from app.services.recommendation_verifications import _evaluate, execute_verification


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
    assert len(DEFINITIONS) == 16
    assert len({definition.key for definition in DEFINITIONS}) == 16
    assert recommendation_for_issue_type("internally_linked_404").key == (
        "repair_broken_internal_link"
    )
    assert recommendation_for_issue_type("orphan_page").key == "resolve_orphan_structure"
    assert (
        recommendation_for_issue_type("important_page_few_internal_links").key
        == "connect_orphan_page"
    )
    assert recommendation_for_issue_type("thin_content") is None


def test_orphan_task_requires_structure_decision_before_link_advice(client) -> None:  # type: ignore[no-untyped-def]
    customer = client.post("/api/v1/clients", json={"name": "Structure client"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Structure site",
            "base_url": "https://example.com",
        },
    ).json()
    with SessionLocal() as db:
        website_id = UUID(website["id"])
        url = Url(website_id=website_id, normalized_url="https://example.com/orphan")
        db.add(url)
        db.flush()
        issue = Issue(
            website_id=website_id,
            url_id=url.id,
            issue_type="orphan_page",
            category="internal_links",
            severity="medium",
            title="Indexeerbare pagina staat buiten de interne sitestructuur",
            description="De pagina heeft geen interne route.",
            recommended_action="Bepaal eerst of de pagina zelfstandig moet blijven.",
        )
        db.add(issue)
        db.commit()
        issue_id = issue.id

    response = client.post(f"/api/v1/issues/{issue_id}/recommendation-task")

    assert response.status_code == 201
    task = response.json()
    assert task["recommendation_type"] == "resolve_orphan_structure"
    assert task["feasibility"] == "needs_decision"
    assert task["required_input"] == ["Moet deze pagina zelfstandig blijven bestaan?"]
    assert "Beslis eerst" in task["steps"][0]
    assert all("Voeg contextuele links" not in step for step in task["steps"])
    detail = client.get(f"/api/v1/recommendation-tasks/{task['id']}").json()
    assert detail["urls"][0]["role"] == "changed"
    plan = client.get(
        f"/api/v1/recommendation-tasks/{task['id']}/verification-plan"
    ).json()
    assert plan["supported"] is False


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
                RecommendationVerification(
                    task_id=task.id,
                    verification_type="repair_broken_internal_link",
                    scope_version="1",
                    status="queued",
                    scope={"source": [str(url.id)]},
                    rules=[{"rule": "source_link_removed_or_updated"}],
                ),
            ]
        )
        db.commit()

        assert db.query(RecommendationTask).filter_by(website_id=website.id).count() == 1
        assert db.query(RecommendationTaskIssue).filter_by(task_id=task.id).count() == 1
        assert db.query(RecommendationTaskUrl).filter_by(task_id=task.id).count() == 1
        assert db.query(RecommendationTaskEvent).filter_by(task_id=task.id).count() == 1
        assert db.query(RecommendationFeedback).filter_by(task_id=task.id).count() == 1
        assert db.query(RecommendationVerification).filter_by(task_id=task.id).count() == 1


def test_task_constraints_reject_invalid_status_and_effort() -> None:
    with SessionLocal() as db:
        _website, _url, _issue, task = _task_fixture(db)
        task.status = "verification_running"
        task.effort_min_minutes = 60
        task.effort_max_minutes = 30
        with pytest.raises(IntegrityError):
            db.commit()


def test_recommendation_task_api_lifecycle(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    queued: list[str] = []
    monkeypatch.setattr(
        "app.services.recommendation_verifications.enqueue_recommendation_verification",
        lambda verification_id, **_kwargs: queued.append(verification_id),
    )
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
        url = Url(website_id=website_id, normalized_url="https://example.com/missing-target")
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
    assert len(definitions.json()) == 16

    created = client.post(f"/api/v1/issues/{issue_id}/recommendation-task")
    assert created.status_code == 201
    task = created.json()
    task_id = task["id"]
    assert task["recommendation_type"] == "repair_broken_internal_link"
    assert task["primary_role"] == "content"
    assert task["priority"] == "high"
    assert task["status"] == "open"
    assert task["verification_status"] == "not_requested"
    initial_plan = client.get(
        f"/api/v1/recommendation-tasks/{task_id}/verification-plan"
    )
    assert initial_plan.status_code == 200
    assert initial_plan.json()["supported"] is True
    assert initial_plan.json()["scope_version"] == "2"
    assert initial_plan.json()["required_roles"] == ["source", "broken_target"]
    assert initial_plan.json()["present_roles"] == ["broken_target"]
    assert initial_plan.json()["missing_roles"] == ["source"]
    assert initial_plan.json()["can_request"] is False
    assert "eerst als uitgevoerd" in initial_plan.json()["blocking_reason"]
    assert (
        client.get(f"/api/v1/recommendation-tasks/{task_id}/verifications").json()
        == []
    )

    duplicate = client.post(f"/api/v1/issues/{issue_id}/recommendation-task")
    assert duplicate.status_code == 409

    tasks = client.get(f"/api/v1/websites/{website['id']}/recommendation-tasks")
    assert tasks.status_code == 200
    assert [item["id"] for item in tasks.json()] == [task_id]

    detail = client.get(f"/api/v1/recommendation-tasks/{task_id}")
    assert detail.status_code == 200
    assert detail.json()["issue_ids"] == [str(issue_id)]
    assert detail.json()["urls"][0]["role"] == "broken_target"
    assert detail.json()["urls"][0]["url"] == "https://example.com/missing-target"
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
    incomplete_plan = client.get(
        f"/api/v1/recommendation-tasks/{task_id}/verification-plan"
    ).json()
    assert incomplete_plan["can_request"] is False
    assert "source" in incomplete_plan["blocking_reason"]
    invalid_role = client.post(
        f"/api/v1/recommendation-tasks/{task_id}/urls",
        json={"role": "target", "url": "https://example.com/source"},
    )
    assert invalid_role.status_code == 422
    outside_scope = client.post(
        f"/api/v1/recommendation-tasks/{task_id}/urls",
        json={"role": "source", "url": "https://outside.example.net/source"},
    )
    assert outside_scope.status_code == 422
    source_scope = client.post(
        f"/api/v1/recommendation-tasks/{task_id}/urls",
        json={"role": "source", "url": "https://example.com/source"},
    )
    assert source_scope.status_code == 201
    assert source_scope.json()["role"] == "source"
    assert source_scope.json()["is_user_supplied"] is True

    duplicate_scope = client.post(
        f"/api/v1/recommendation-tasks/{task_id}/urls",
        json={"role": "source", "url": "https://example.com/source"},
    )
    assert duplicate_scope.status_code == 422
    complete_plan = client.get(
        f"/api/v1/recommendation-tasks/{task_id}/verification-plan"
    ).json()
    assert complete_plan["can_request"] is True
    assert complete_plan["missing_roles"] == []
    assert complete_plan["url_count"] == 2
    removed_scope = client.delete(
        f"/api/v1/recommendation-tasks/{task_id}/urls/{source_scope.json()['id']}"
    )
    assert removed_scope.status_code == 204
    assert (
        client.get(
            f"/api/v1/recommendation-tasks/{task_id}/verification-plan"
        ).json()["can_request"]
        is False
    )
    restored_scope = client.post(
        f"/api/v1/recommendation-tasks/{task_id}/urls",
        json={"role": "source", "url": "https://example.com/source"},
    )
    assert restored_scope.status_code == 201
    requested = client.post(
        f"/api/v1/recommendation-tasks/{task_id}/verifications"
    )
    assert requested.status_code == 202
    assert requested.json()["status"] == "queued"
    assert queued == [requested.json()["id"]]
    duplicate_verification = client.post(
        f"/api/v1/recommendation-tasks/{task_id}/verifications"
    )
    assert duplicate_verification.status_code == 409
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


def test_targeted_broken_link_verification_only_fetches_selected_urls(
    monkeypatch,
) -> None:
    fetched: list[str] = []

    def fake_fetch(url: str, **_kwargs: object) -> FetchResult:
        fetched.append(url)
        return FetchResult(
            requested_url=url,
            final_url=url,
            status_code=200,
            redirect_chain=[],
            headers={"content-type": "text/html"},
            content=b"<html><head><title>Bron</title></head><body>Hersteld</body></html>",
            response_time_ms=2,
        )

    monkeypatch.setattr(
        "app.services.recommendation_verifications.fetch_url",
        fake_fetch,
    )
    monkeypatch.setattr("app.jobs._load_robots_rules", lambda _db, _job: None)
    with SessionLocal() as db:
        website, source, _issue, task = _task_fixture(db)
        task.status = "implemented"
        target = Url(
            website_id=website.id,
            normalized_url="https://example.com/defect",
        )
        unrelated = Url(
            website_id=website.id,
            normalized_url="https://example.com/niet-in-scope",
        )
        db.add_all([target, unrelated])
        db.flush()
        db.add_all(
            [
                RecommendationTaskUrl(task_id=task.id, url_id=source.id, role="source"),
                RecommendationTaskUrl(
                    task_id=task.id,
                    url_id=target.id,
                    role="broken_target",
                ),
            ]
        )
        job = CrawlJob(
            website_id=website.id,
            job_type="recommendation_verification",
            settings_snapshot={},
        )
        db.add(job)
        db.flush()
        verification = RecommendationVerification(
            task_id=task.id,
            crawl_job_id=job.id,
            verification_type=task.recommendation_type,
            scope_version="2",
            scope={
                "urls": [
                    {
                        "url_id": str(source.id),
                        "role": "source",
                        "url": source.normalized_url,
                    },
                    {
                        "url_id": str(target.id),
                        "role": "broken_target",
                        "url": target.normalized_url,
                    },
                ]
            },
        )
        db.add(verification)
        db.commit()
        verification_id = verification.id
        interval_before = website.settings.full_crawl_interval

    execute_verification(str(verification_id))

    with SessionLocal() as db:
        verification = db.get(RecommendationVerification, verification_id)
        assert verification is not None
        assert verification.status == "passed"
        assert verification.result["outcome"] == "resolved"
        assert fetched == ["https://example.com/source"]
        assert verification.result["checked_url_ids"] == [str(source.id)]
        run = db.query(CrawlRun).filter_by(crawl_job_id=verification.crawl_job_id).one()
        assert run.crawl_type == "recommendation_verification"
        assert db.query(UrlSnapshot).filter_by(crawl_run_id=run.id).count() == 1
        assert db.get(Website, website.id).settings.full_crawl_interval == interval_before

    execute_verification(str(verification_id))
    assert fetched == ["https://example.com/source"]


def test_additional_verification_rules_resolve_redirect_missing_and_indexability() -> None:
    with SessionLocal() as db:
        website, source, _issue, _task = _task_fixture(db)
        redirect = Url(
            website_id=website.id,
            normalized_url="https://example.com/redirect",
        )
        old = Url(
            website_id=website.id,
            normalized_url="https://example.com/old",
        )
        replacement = Url(
            website_id=website.id,
            normalized_url="https://example.com/new",
        )
        changed = Url(
            website_id=website.id,
            normalized_url="https://example.com/indexable",
        )
        onpage = Url(
            website_id=website.id,
            normalized_url="https://example.com/onpage",
        )
        db.add_all([redirect, old, replacement, changed, onpage])
        db.flush()
        job = CrawlJob(
            website_id=website.id,
            job_type="recommendation_verification",
        )
        db.add(job)
        db.flush()
        run = CrawlRun(
            crawl_job_id=job.id,
            website_id=website.id,
            crawl_type="recommendation_verification",
        )
        db.add(run)
        db.flush()
        db.add_all(
            [
                UrlSnapshot(
                    url_id=source.id,
                    crawl_run_id=run.id,
                    requested_url=source.normalized_url,
                    final_url=source.normalized_url,
                    status_code=200,
                    is_indexable=True,
                ),
                UrlSnapshot(
                    url_id=old.id,
                    crawl_run_id=run.id,
                    requested_url=old.normalized_url,
                    final_url=replacement.normalized_url,
                    status_code=200,
                    redirect_chain=[
                        {
                            "url": old.normalized_url,
                            "status_code": 301,
                            "target": replacement.normalized_url,
                        }
                    ],
                    is_indexable=True,
                ),
                UrlSnapshot(
                    url_id=replacement.id,
                    crawl_run_id=run.id,
                    requested_url=replacement.normalized_url,
                    final_url=replacement.normalized_url,
                    status_code=200,
                    is_indexable=True,
                ),
                UrlSnapshot(
                    url_id=changed.id,
                    crawl_run_id=run.id,
                    requested_url=changed.normalized_url,
                    final_url=changed.normalized_url,
                    status_code=200,
                    meta_robots="index,follow",
                    is_indexable=True,
                ),
                UrlSnapshot(
                    url_id=onpage.id,
                    crawl_run_id=run.id,
                    requested_url=onpage.normalized_url,
                    final_url=onpage.normalized_url,
                    status_code=200,
                    title="Unieke paginatitel",
                    meta_description="Unieke en relevante omschrijving.",
                    headings={"h1": ["Heldere primaire kop"]},
                    schema_types=["BreadcrumbList"],
                    schema_data=[{"@type": "BreadcrumbList"}],
                    is_indexable=True,
                ),
            ]
        )
        db.flush()

        redirect_rules = _evaluate(
            db,
            "replace_redirected_internal_link",
            {
                "source": [source],
                "target": [redirect],
                "expected_target": [replacement],
            },
            run.id,
        )
        missing_rules = _evaluate(
            db,
            "restore_or_redirect_missing_page",
            {"old": [old], "new": [replacement]},
            run.id,
        )
        indexability_rules = _evaluate(
            db,
            "correct_indexability",
            {"changed": [changed]},
            run.id,
        )
        title_rules = _evaluate(
            db,
            "add_or_correct_title",
            {"changed": [onpage]},
            run.id,
        )
        duplicate_title_rules = _evaluate(
            db,
            "add_or_correct_title",
            {"changed": [onpage], "sample": [onpage]},
            run.id,
        )
        heading_rules = _evaluate(
            db,
            "add_primary_heading",
            {"changed": [onpage]},
            run.id,
        )
        description_rules = _evaluate(
            db,
            "add_meta_description",
            {"changed": [onpage]},
            run.id,
        )
        schema_rules = _evaluate(
            db,
            "repair_structured_data",
            {"changed": [onpage]},
            run.id,
            issue_type="missing_breadcrumb_schema",
        )

        assert {rule["status"] for rule in redirect_rules} == {"passed"}
        assert {rule["status"] for rule in missing_rules} == {"passed"}
        assert {rule["status"] for rule in indexability_rules} == {"passed"}
        assert {rule["status"] for rule in title_rules} == {"passed"}
        assert duplicate_title_rules[-1]["status"] == "failed"
        assert {rule["status"] for rule in heading_rules} == {"passed"}
        assert {rule["status"] for rule in description_rules} == {"passed"}
        assert {rule["status"] for rule in schema_rules} == {"passed"}


def test_redirect_and_canonical_verification_validate_destination_quality() -> None:
    with SessionLocal() as db:
        website, source, _issue, _task = _task_fixture(db)
        expected = Url(
            website_id=website.id,
            normalized_url="https://example.com/preferred",
        )
        db.add(expected)
        db.flush()
        job = CrawlJob(
            website_id=website.id,
            job_type="recommendation_verification",
        )
        db.add(job)
        db.flush()
        run = CrawlRun(
            crawl_job_id=job.id,
            website_id=website.id,
            crawl_type="recommendation_verification",
        )
        db.add(run)
        db.flush()
        db.add_all(
            [
                UrlSnapshot(
                    url_id=source.id,
                    crawl_run_id=run.id,
                    requested_url=source.normalized_url,
                    final_url=expected.normalized_url,
                    status_code=200,
                    redirect_chain=[
                        {
                            "url": source.normalized_url,
                            "status_code": 301,
                            "target": expected.normalized_url,
                        }
                    ],
                    canonical=expected.normalized_url,
                    is_indexable=True,
                ),
                UrlSnapshot(
                    url_id=expected.id,
                    crawl_run_id=run.id,
                    requested_url=expected.normalized_url,
                    final_url=expected.normalized_url,
                    status_code=200,
                    canonical=expected.normalized_url,
                    is_indexable=True,
                ),
            ]
        )
        db.flush()

        redirect_rules = _evaluate(
            db,
            "fix_redirect_chain_or_loop",
            {"source": [source], "expected_target": [expected]},
            run.id,
        )
        canonical_rules = _evaluate(
            db,
            "correct_canonical",
            {"source": [source], "expected_canonical": [expected]},
            run.id,
        )

        assert {rule["status"] for rule in redirect_rules} == {"passed"}
        assert {rule["status"] for rule in canonical_rules} == {"passed"}

        destination = (
            db.query(UrlSnapshot)
            .filter_by(crawl_run_id=run.id, url_id=expected.id)
            .one_or_none()
        )
        assert destination is not None
        destination.is_indexable = False
        destination.canonical = "https://example.com/other"
        db.flush()

        failed_redirect = _evaluate(
            db,
            "fix_redirect_chain_or_loop",
            {"source": [source], "expected_target": [expected]},
            run.id,
        )
        failed_canonical = _evaluate(
            db,
            "correct_canonical",
            {"source": [source], "expected_canonical": [expected]},
            run.id,
        )

        assert failed_redirect[-1]["status"] == "failed"
        assert failed_canonical[-1]["status"] == "failed"


def test_grouped_broken_link_evidence_enriches_verification_scope(client) -> None:  # type: ignore[no-untyped-def]
    customer = client.post("/api/v1/clients", json={"name": "Scope client"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Scope website",
            "base_url": "https://scope.example.com",
        },
    ).json()
    with SessionLocal() as db:
        website_id = UUID(website["id"])
        source = Url(
            website_id=website_id,
            normalized_url="https://scope.example.com/source",
        )
        target = Url(
            website_id=website_id,
            normalized_url="https://scope.example.com/missing",
        )
        db.add_all([source, target])
        db.flush()
        issue = Issue(
            website_id=website_id,
            url_id=source.id,
            issue_type="multiple_broken_internal_links",
            category="internal_links",
            severity="high",
            title="Meerdere defecte links",
            description="De bronpagina bevat defecte links.",
            recommended_action="Herstel de links.",
        )
        job = CrawlJob(
            website_id=website_id,
            job_type="full_site_crawl",
            status="succeeded",
        )
        db.add_all([issue, job])
        db.flush()
        run = CrawlRun(
            crawl_job_id=job.id,
            website_id=website_id,
            crawl_type="full_site_crawl",
            status="succeeded",
        )
        db.add(run)
        db.flush()
        db.add(
            IssueOccurrence(
                issue_id=issue.id,
                crawl_run_id=run.id,
                evidence={
                    "broken_links": [
                        {"target_url": "https://scope.example.com/missing"}
                    ]
                },
            )
        )
        db.commit()
        issue_id = issue.id

    created = client.post(f"/api/v1/issues/{issue_id}/recommendation-task")
    assert created.status_code == 201
    plan = client.get(
        f"/api/v1/recommendation-tasks/{created.json()['id']}/verification-plan"
    ).json()
    assert plan["present_roles"] == ["broken_target", "source"]
    assert plan["missing_roles"] == []


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
        browser.get(
            f"/api/v1/recommendation-tasks/{task_id}/verification-plan"
        ).status_code
        == 200
    )
    assert (
        browser.get(
            f"/api/v1/recommendation-tasks/{task_id}/verifications"
        ).status_code
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
            f"/api/v1/recommendation-tasks/{task_id}/urls",
            json={
                "role": "source",
                "url": "https://readonly.example.com/source",
            },
        ).status_code
        == 403
    )
    assert (
        browser.delete(
            f"/api/v1/recommendation-tasks/{task_id}/urls/"
            "00000000-0000-0000-0000-000000000001"
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

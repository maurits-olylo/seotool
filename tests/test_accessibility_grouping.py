import uuid

from sqlalchemy import select

from app.core.security import Principal
from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.issues import Issue, IssueOccurrence
from app.models.recommendations import (
    RecommendationTaskIssue,
    RecommendationTaskUrl,
    RecommendationVerification,
)
from app.models.rendering import RenderObservation
from app.models.website import Website, WebsiteSettings
from app.services.accessibility.grouping import component_signature
from app.services.recommendation_tasks import create_task_from_issue
from app.services.recommendation_verifications import execute_verification, request_verification


def test_component_signature_ignores_positional_index() -> None:
    first = component_signature("button-name", ["nav > button:nth-child(2)"])
    second = component_signature("button-name", ["nav > button:nth-child(8)"])

    assert first == second
    assert first != component_signature("link-name", ["nav > button:nth-child(2)"])


def test_accessibility_task_links_and_rechecks_same_component_across_pages(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    with SessionLocal() as db:
        website = Website(
            client=Client(name="Accessibility grouping client"),
            name="Accessibility grouping site",
            base_url="https://example.com",
            settings=WebsiteSettings(),
        )
        db.add(website)
        db.flush()
        urls = [
            Url(website_id=website.id, normalized_url=f"https://example.com/page-{number}")
            for number in range(3)
        ]
        job = CrawlJob(website_id=website.id, job_type="full_site_crawl")
        db.add_all([*urls, job])
        db.flush()
        run = CrawlRun(
            crawl_job_id=job.id,
            website_id=website.id,
            crawl_type="full_site_crawl",
        )
        db.add(run)
        db.flush()
        db.add_all(
            UrlSnapshot(
                url_id=url.id,
                crawl_run_id=run.id,
                requested_url=url.normalized_url,
                final_url=url.normalized_url,
                status_code=200,
                content_type="text/html",
                is_indexable=True,
            )
            for url in urls
        )
        shared = component_signature("button-name", ["header > button:nth-child(2)"])
        other = component_signature("button-name", ["main > button.buy"])
        issues = [
            Issue(
                website_id=website.id,
                url_id=url.id,
                issue_type="accessibility_button_name",
                category="accessibility",
                severity="high",
                title="Knop heeft geen toegankelijke naam",
                description="Automatische controle.",
                recommended_action="Geef de knop een naam.",
            )
            for url in urls
        ]
        db.add_all(issues)
        db.flush()
        db.add_all(
            IssueOccurrence(
                issue_id=issue.id,
                crawl_run_id=run.id,
                evidence={
                    "accessibility": {
                        "component_signature": signature,
                        "rule_id": "button-name",
                    }
                },
            )
            for issue, signature in zip(issues, [shared, shared, other], strict=True)
        )
        db.commit()

        task = create_task_from_issue(
            db,
            issue=issues[0],
            principal=Principal(user_id=None, role="superuser", is_api_key=True),
        )

        linked_issue_ids = set(
            db.scalars(
                select(RecommendationTaskIssue.issue_id).where(
                    RecommendationTaskIssue.task_id == task.id
                )
            )
        )
        scoped_url_ids = set(
            db.scalars(
                select(RecommendationTaskUrl.url_id).where(
                    RecommendationTaskUrl.task_id == task.id
                )
            )
        )
        assert task.recommendation_type == "repair_accessibility_component"
        assert linked_issue_ids == {issues[0].id, issues[1].id}
        assert scoped_url_ids == {urls[0].id, urls[1].id}
        assert task.verification_spec["linked_issue_ids"] == [
            str(issues[0].id),
            str(issues[1].id),
        ]
        task.status = "implemented"
        db.commit()

        queued: list[dict[str, object]] = []
        monkeypatch.setattr(
            "app.services.recommendation_verifications.enqueue_recommendation_verification",
            lambda _verification_id, **kwargs: queued.append(kwargs) or True,
        )
        verification = request_verification(
            db,
            task=task,
            principal=Principal(user_id=None, role="superuser", is_api_key=True),
        )
        verification_id = str(verification.id)
        assert queued[0]["queue_name"] == "renders"

    def finish_render(observation_id: str) -> None:
        with SessionLocal() as render_db:
            observation = render_db.get(RenderObservation, uuid.UUID(observation_id))
            assert observation is not None
            observation.status = "succeeded"
            observation.comparison = {
                "accessibility": {
                    "engine": "axe-core",
                    "engine_version": "4.12.1",
                    "violations": [],
                    "incomplete": [],
                }
            }
            render_db.commit()

    monkeypatch.setattr(
        "app.services.recommendation_verifications.execute_render_observation",
        finish_render,
    )
    execute_verification(verification_id)

    with SessionLocal() as db:
        verification = db.get(RecommendationVerification, uuid.UUID(verification_id))
        assert verification is not None
        assert verification.status == "passed"
        assert verification.result["outcome"] == "resolved"
        assert verification.result["rule_counts"] == {
            "passed": 2,
            "failed": 0,
            "error": 0,
        }
        assert len(verification.result["render_observation_ids"]) == 2

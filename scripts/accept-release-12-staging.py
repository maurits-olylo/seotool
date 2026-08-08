import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.security import Principal
from app.db.session import SessionLocal
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.issues import Issue, IssueOccurrence
from app.models.recommendations import (
    RecommendationTask,
    RecommendationTaskIssue,
    RecommendationVerification,
)
from app.models.website import Website
from app.services.accessibility.grouping import component_signature
from app.services.html_extraction import extract_page
from app.services.recommendation_tasks import create_task_from_issue
from app.services.recommendation_verifications import execute_verification, request_verification
from app.services.staging_render_acceptance import (
    STAGING_ACCESSIBILITY_ACCEPTANCE_URLS,
    staging_accessibility_acceptance_html,
)

FIXTURE_MARKER = "release_12_accessibility_component_workflow"
ISSUE_TYPE = "accessibility_button_name"


def _prepare() -> tuple[str, str]:
    extracted = extract_page(
        staging_accessibility_acceptance_html(resolved=False),
        STAGING_ACCESSIBILITY_ACCEPTANCE_URLS[0],
    )
    signature = component_signature(
        "button-name", ["button.shared-acceptance-action"]
    )
    if signature is None:
        raise RuntimeError("Component signature could not be created")
    with SessionLocal() as db:
        website = db.scalar(
            select(Website).where(Website.name.like("[STAGING]%")).order_by(Website.created_at)
        )
        if website is None:
            raise RuntimeError("No synthetic staging website exists")
        urls: list[Url] = []
        for value in STAGING_ACCESSIBILITY_ACCEPTANCE_URLS:
            url = db.scalar(
                select(Url).where(
                    Url.website_id == website.id,
                    Url.normalized_url == value,
                )
            )
            if url is None:
                url = Url(
                    website_id=website.id,
                    normalized_url=value,
                    current_status_code=200,
                    current_final_url=value,
                    is_active=True,
                    is_indexable=False,
                    page_type="staging_acceptance",
                )
                db.add(url)
                db.flush()
            urls.append(url)

        job = CrawlJob(
            website_id=website.id,
            job_type="full_page_analysis",
            status="succeeded",
            finished_at=datetime.now(UTC),
            settings_snapshot={"acceptance_fixture": FIXTURE_MARKER},
        )
        db.add(job)
        db.flush()
        run = CrawlRun(
            crawl_job_id=job.id,
            website_id=website.id,
            crawl_type="full_page_analysis",
            status="succeeded",
            finished_at=datetime.now(UTC),
            discovered_urls=2,
            crawled_urls=2,
            html_urls=2,
        )
        db.add(run)
        db.flush()

        issues: list[Issue] = []
        for url in urls:
            issue = db.scalar(
                select(Issue).where(
                    Issue.website_id == website.id,
                    Issue.url_id == url.id,
                    Issue.issue_type == ISSUE_TYPE,
                )
            )
            if issue is None:
                issue = Issue(
                    website_id=website.id,
                    url_id=url.id,
                    issue_type=ISSUE_TYPE,
                    category="accessibility",
                    severity="high",
                    confidence="high",
                    title="Knop heeft geen toegankelijke naam",
                    description="Synthetisch componentprobleem voor stagingacceptatie.",
                    recommended_action="Geef het gedeelde component een toegankelijke naam.",
                )
                db.add(issue)
                db.flush()
            else:
                issue.status = "new"
                issue.resolved_at = None
                issue.verified_at = None
            snapshot = UrlSnapshot(
                url_id=url.id,
                crawl_run_id=run.id,
                requested_url=url.normalized_url,
                final_url=url.normalized_url,
                status_code=200,
                content_type="text/html; charset=utf-8",
                title=extracted.title,
                html_lang=extracted.html_lang,
                headings=extracted.headings,
                word_count=extracted.word_count,
                main_content=extracted.main_content,
                html_hash=extracted.html_hash,
                main_content_hash=extracted.main_content_hash,
                metadata_hash=extracted.metadata_hash,
                links_hash=extracted.links_hash,
                schema_hash=extracted.schema_hash,
                is_indexable=False,
            )
            db.add(snapshot)
            db.flush()
            occurrence = db.scalar(
                select(IssueOccurrence).where(
                    IssueOccurrence.issue_id == issue.id,
                    IssueOccurrence.crawl_run_id == run.id,
                )
            )
            if occurrence is None:
                db.add(
                    IssueOccurrence(
                        issue_id=issue.id,
                        crawl_run_id=run.id,
                        snapshot_id=snapshot.id,
                        evidence={
                            "accessibility": {
                                "engine": "axe-core",
                                "engine_version": "4.12.1",
                                "rule_id": "button-name",
                                "component_signature": signature,
                            },
                            "acceptance_fixture": FIXTURE_MARKER,
                        },
                    )
                )
            issues.append(issue)
        db.commit()
        task = create_task_from_issue(
            db,
            issue=issues[0],
            principal=Principal(user_id=None, role="superuser", is_api_key=True),
        )
        linked_count = len(
            list(
                db.scalars(
                    select(RecommendationTaskIssue).where(
                        RecommendationTaskIssue.task_id == task.id
                    )
                )
            )
        )
        if linked_count != 2:
            raise RuntimeError(f"Expected two grouped issues, got {linked_count}")
        task.status = "implemented"
        task.implemented_at = datetime.now(UTC)
        db.commit()
        verification = request_verification(
            db,
            task=task,
            principal=Principal(user_id=None, role="superuser", is_api_key=True),
        )
        return str(task.id), str(verification.id)


def main() -> None:
    task_id, verification_id = _prepare()
    execute_verification(verification_id)
    with SessionLocal() as db:
        task = db.get(RecommendationTask, UUID(task_id))
        verification = db.get(RecommendationVerification, UUID(verification_id))
        if task is None or verification is None:
            raise RuntimeError("Acceptance records disappeared")
        if task.status != "closed" or verification.status != "passed":
            raise RuntimeError(
                f"Workflow did not resolve: task={task.status} verification={verification.status}"
            )
        if len(verification.result.get("render_observation_ids", [])) != 2:
            raise RuntimeError("Expected two render observations")
        print(
            {
                "status": "release_12_phase_c_staging_ok",
                "task_id": task_id,
                "verification_id": verification_id,
                "grouped_issues": 2,
                "render_observations": 2,
            }
        )
if __name__ == "__main__":
    main()

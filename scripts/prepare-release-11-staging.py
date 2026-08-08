import json
import os
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.config import get_settings
from app.core.queue import enqueue_render_observation
from app.db.session import SessionLocal
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.issues import Issue, IssueOccurrence
from app.models.rendering import RenderObservation
from app.models.website import Website
from app.services.html_extraction import extract_page
from app.services.staging_render_acceptance import (
    STAGING_RENDER_ACCEPTANCE_URL,
    staging_render_acceptance_html,
)

FIXTURE_MARKER = "release_11_missing_h1_resolution"


def _set_page_state(*, resolved: bool) -> None:
    payload = json.dumps({"resolved": resolved}).encode()
    request = urllib.request.Request(
        "http://127.0.0.1:8000/staging/render-acceptance",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": os.environ["API_KEY"],
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        if response.status != 200:
            raise RuntimeError("Acceptance page state could not be updated")


def _prepare_records() -> tuple[str, str]:
    extracted = extract_page(
        staging_render_acceptance_html(resolved=False),
        STAGING_RENDER_ACCEPTANCE_URL,
    )
    with SessionLocal() as db:
        website = db.scalar(
            select(Website).where(Website.name.like("[STAGING]%")).order_by(Website.created_at)
        )
        if website is None:
            raise RuntimeError("No synthetic staging website exists")

        url = db.scalar(
            select(Url).where(
                Url.website_id == website.id,
                Url.normalized_url == STAGING_RENDER_ACCEPTANCE_URL,
            )
        )
        if url is None:
            url = Url(
                website_id=website.id,
                normalized_url=STAGING_RENDER_ACCEPTANCE_URL,
                current_status_code=200,
                current_final_url=STAGING_RENDER_ACCEPTANCE_URL,
                is_active=True,
                is_indexable=False,
                page_type="staging_acceptance",
            )
            db.add(url)
            db.flush()

        issue = db.scalar(
            select(Issue).where(
                Issue.website_id == website.id,
                Issue.issue_type == "staging_effect_acceptance",
            )
        )
        if issue is None:
            issue = db.scalar(
                select(Issue).where(
                    Issue.website_id == website.id,
                    Issue.url_id == url.id,
                    Issue.issue_type == "missing_h1",
                )
            )
        if issue is None:
            issue = Issue(
                website_id=website.id,
                url_id=url.id,
                issue_type="missing_h1",
                category="onpage",
                severity="low",
                confidence="high",
                status="review",
                title="Synthetische visuele inspectie",
                description="De H1 ontbreekt in de historische stagingmeting.",
                recommended_action="Controleer de historische opname en voer live hercontrole uit.",
            )
            db.add(issue)
        else:
            issue.url_id = url.id
            issue.issue_type = "missing_h1"
            issue.category = "onpage"
            issue.severity = "low"
            issue.confidence = "high"
            issue.status = "review"
            issue.title = "Synthetische visuele inspectie"
            issue.description = "De H1 ontbreekt in de historische stagingmeting."
            issue.recommended_action = (
                "Controleer de historische opname en voer live hercontrole uit."
            )
        db.flush()

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
            discovered_urls=1,
            crawled_urls=1,
            html_urls=1,
        )
        db.add(run)
        db.flush()
        snapshot = UrlSnapshot(
            url_id=url.id,
            crawl_run_id=run.id,
            requested_url=STAGING_RENDER_ACCEPTANCE_URL,
            final_url=STAGING_RENDER_ACCEPTANCE_URL,
            status_code=200,
            redirect_chain=[],
            content_type="text/html; charset=utf-8",
            title=extracted.title,
            meta_description=extracted.meta_description,
            canonical=extracted.canonical,
            meta_robots=extracted.meta_robots,
            html_lang=extracted.html_lang,
            headings=extracted.headings,
            word_count=extracted.word_count,
            main_content=extracted.main_content,
            schema_types=extracted.schema_types,
            schema_data=extracted.schema_data,
            html_hash=extracted.html_hash,
            main_content_hash=extracted.main_content_hash,
            metadata_hash=extracted.metadata_hash,
            links_hash=extracted.links_hash,
            schema_hash=extracted.schema_hash,
            is_indexable=False,
        )
        db.add(snapshot)
        db.flush()
        db.add(
            IssueOccurrence(
                issue_id=issue.id,
                crawl_run_id=run.id,
                snapshot_id=snapshot.id,
                evidence={"h1_count": 0, "acceptance_fixture": FIXTURE_MARKER},
            )
        )
        observation = RenderObservation(
            website_id=website.id,
            url_id=url.id,
            source_snapshot_id=snapshot.id,
            status="pending",
            trigger_reasons=["staging_acceptance", FIXTURE_MARKER],
        )
        db.add(observation)
        db.commit()
        return str(issue.id), str(observation.id)


def _wait_for_render(observation_id: str) -> str:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        with SessionLocal() as db:
            observation = db.get(RenderObservation, UUID(observation_id))
            if observation is None:
                raise RuntimeError("Acceptance render observation disappeared")
            if observation.status == "succeeded":
                if not observation.screenshot_key:
                    raise RuntimeError("Acceptance render succeeded without screenshot")
                return observation.status
            if observation.status == "failed":
                raise RuntimeError(observation.error_message or "Acceptance render failed")
        time.sleep(2)
    raise RuntimeError("Acceptance render did not finish within 90 seconds")


def _resolve_legacy_fixture_noise() -> None:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        issues = list(
            db.scalars(
                select(Issue)
                .join(Url, Url.id == Issue.url_id)
                .where(
                    Url.normalized_url == STAGING_RENDER_ACCEPTANCE_URL,
                    Issue.issue_type == "javascript_metadata_conflict",
                    Issue.status.not_in(("verified", "ignored", "accepted_risk")),
                )
            )
        )
        for issue in issues:
            issue.status = "verified"
            issue.resolved_at = now
            issue.verified_at = now
        db.commit()


def main() -> None:
    settings = get_settings()
    if settings.app_env != "staging" or not settings.rendering_enabled:
        raise RuntimeError("This fixture requires staging with rendering enabled")
    _set_page_state(resolved=False)
    issue_id, observation_id = _prepare_records()
    if not enqueue_render_observation(observation_id, website_id=_website_id(observation_id)):
        raise RuntimeError("Acceptance render could not be queued")
    render_status = _wait_for_render(observation_id)
    _set_page_state(resolved=True)
    _resolve_legacy_fixture_noise()
    print(
        {
            "status": "release_11_staging_fixture_ready",
            "issue_id": issue_id,
            "observation_id": observation_id,
            "render_status": render_status,
            "page_state": "resolved",
        }
    )


def _website_id(observation_id: str) -> str:
    with SessionLocal() as db:
        observation = db.get(RenderObservation, UUID(observation_id))
        if observation is None:
            raise RuntimeError("Acceptance render observation does not exist")
        return str(observation.website_id)


if __name__ == "__main__":
    main()

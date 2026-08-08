import uuid

import structlog
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.common import utc_now
from app.models.crawl import UrlLink, UrlSnapshot
from app.models.discovery import Url
from app.models.rendering import RenderObservation
from app.services.browser_renderer import render_page_html
from app.services.html_extraction import extract_page
from app.services.issue_engine import reconcile_issues
from app.services.render_analysis import compare_rendered_page, render_issue_signals
from app.services.render_artifacts import store_render_screenshot

logger = structlog.get_logger()
RENDER_ISSUE_TYPES = {
    "javascript_dependent_content",
    "rendered_content_missing",
    "javascript_only_links",
    "javascript_metadata_conflict",
}


def execute_render_observation(observation_id: str) -> None:
    parsed_id = uuid.UUID(observation_id)
    try:
        with SessionLocal() as db:
            observation = db.get(RenderObservation, parsed_id)
            if observation is None:
                raise ValueError("Render observation does not exist")
            snapshot = db.get(UrlSnapshot, observation.source_snapshot_id)
            url = db.get(Url, observation.url_id)
            if snapshot is None or url is None:
                raise ValueError("Render observation source no longer exists")
            observation.status = "running"
            observation.error_message = None
            db.commit()

            result = render_page_html(url.normalized_url)
            rendered = extract_page(result.html, url.normalized_url)
            static_links = set(
                db.scalars(
                    select(UrlLink.target_url).where(
                        UrlLink.crawl_run_id == snapshot.crawl_run_id,
                        UrlLink.source_url_id == url.id,
                        UrlLink.is_internal.is_(True),
                    )
                )
            )
            comparison = compare_rendered_page(
                snapshot, rendered, static_internal_links=static_links
            )
            signals = render_issue_signals(comparison)
            reconcile_issues(
                db,
                website_id=observation.website_id,
                url_id=url.id,
                crawl_run_id=snapshot.crawl_run_id,
                snapshot_id=snapshot.id,
                signals=signals,
                checked_issue_types=RENDER_ISSUE_TYPES,
            )
            observation.status = "succeeded"
            observation.rendered_at = utc_now()
            observation.browser_name = result.browser_name
            observation.rendered_word_count = rendered.word_count
            observation.rendered_main_content_hash = rendered.main_content_hash
            observation.rendered_metadata_hash = rendered.metadata_hash
            observation.rendered_links_hash = rendered.links_hash
            observation.rendered_schema_hash = rendered.schema_hash
            if result.screenshot_png:
                artifact = store_render_screenshot(
                    observation.website_id, observation.id, result.screenshot_png
                )
                observation.screenshot_key = artifact.key
                observation.screenshot_sha256 = artifact.sha256
                observation.screenshot_bytes = artifact.size
                observation.screenshot_width = result.screenshot_width
                observation.screenshot_height = result.screenshot_height
                observation.screenshot_expires_at = artifact.expires_at
            observation.comparison = {
                **comparison,
                "browser_request_count": result.request_count,
                "screenshot_element_boxes": result.element_boxes or [],
                "screenshot_viewport": {
                    "width": result.screenshot_width,
                    "height": result.screenshot_height,
                },
            }
            db.commit()
            logger.info(
                "render_observation_succeeded",
                observation_id=observation_id,
                website_id=str(observation.website_id),
                url_id=str(url.id),
                request_count=result.request_count,
            )
    except Exception as exc:
        with SessionLocal() as db:
            observation = db.get(RenderObservation, parsed_id)
            if observation is not None:
                observation.status = "failed"
                observation.error_message = f"{type(exc).__name__}: {exc}"[:2_000]
                db.commit()
        logger.exception("render_observation_failed", observation_id=observation_id)
        raise

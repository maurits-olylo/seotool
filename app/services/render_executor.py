import uuid

import structlog
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.common import utc_now
from app.models.crawl import UrlLink, UrlSnapshot
from app.models.discovery import Url
from app.models.rendering import RenderObservation
from app.services.accessibility.normalization import (
    accessibility_issue_signals,
    normalize_axe_result,
)
from app.services.accessibility.rule_catalog import ACCESSIBILITY_ISSUE_TYPES
from app.services.browser_renderer import render_page_html
from app.services.html_extraction import ExtractedPage, extract_page
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

            focus_target = observation.comparison.get("inspection_focus")
            absence_target = observation.comparison.get("inspection_absence")
            accessibility_requested = observation.comparison.get("accessibility_requested") is True
            render_options: dict[str, object] = {}
            if isinstance(focus_target, dict):
                render_options["focus_target"] = focus_target
            if accessibility_requested:
                render_options["run_accessibility"] = True
            result = render_page_html(url.normalized_url, **render_options)
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
            accessibility = (
                normalize_axe_result(result.accessibility_result)
                if result.accessibility_result is not None
                else None
            )
            if accessibility is not None:
                signals.extend(accessibility_issue_signals(accessibility))
            reconcile_issues(
                db,
                website_id=observation.website_id,
                url_id=url.id,
                crawl_run_id=snapshot.crawl_run_id,
                snapshot_id=snapshot.id,
                signals=signals,
                checked_issue_types=(
                    RENDER_ISSUE_TYPES | ACCESSIBILITY_ISSUE_TYPES
                    if accessibility_requested
                    else RENDER_ISSUE_TYPES
                ),
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
                "inspection_focus": focus_target if isinstance(focus_target, dict) else None,
                "inspection_focus_applied": result.focus_applied,
                "inspection_focus_status": result.focus_status,
                "inspection_absence": (
                    absence_target if isinstance(absence_target, dict) else None
                ),
                "inspection_absence_status": _absence_status(rendered, absence_target),
                "accessibility_requested": accessibility_requested,
                "accessibility": accessibility,
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


def _absence_status(rendered: ExtractedPage, target: object) -> str:
    if not isinstance(target, dict):
        return "not_requested"
    element_type = target.get("element_type")
    checks = {
        "h1": bool(rendered.headings.get("h1")),
        "title": bool(rendered.title),
        "meta_description": bool(rendered.meta_description),
        "breadcrumb_schema": "BreadcrumbList" in rendered.schema_types,
    }
    if not isinstance(element_type, str) or element_type not in checks:
        return "inconclusive"
    return "present" if checks[element_type] else "still_absent"

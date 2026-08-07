from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crawl import ElementLocation, UrlSnapshot
from app.models.discovery import Url
from app.models.issues import Issue, IssueOccurrence
from app.models.rendering import RenderObservation

MISSING_ELEMENT_TYPES = {
    "missing_h1": "h1",
    "missing_title": "title",
    "missing_meta_description": "meta_description",
    "missing_breadcrumb_schema": "breadcrumb_schema",
}


def build_issue_inspection(
    db: Session,
    *,
    issue: Issue,
    occurrence: IssueOccurrence | None,
    element_payloads: list[dict[str, object]],
) -> dict[str, object]:
    location_ids = {
        item["id"] for item in element_payloads if isinstance(item.get("id"), UUID)
    }
    locations = {
        item.id: item
        for item in db.scalars(
            select(ElementLocation).where(ElementLocation.id.in_(location_ids))
        )
    }
    grouped: dict[UUID, list[dict[str, object]]] = defaultdict(list)
    for payload in element_payloads:
        location = locations.get(payload.get("id"))
        if location is not None:
            grouped[location.snapshot_id].append(_located_target(location, payload))

    pages = [
        _inspection_page(
            db,
            snapshot_id=snapshot_id,
            targets=targets,
            occurrence=occurrence,
        )
        for snapshot_id, targets in grouped.items()
    ]
    missing_type = MISSING_ELEMENT_TYPES.get(issue.issue_type)
    if not pages and missing_type and issue.url_id:
        snapshot = _issue_snapshot(db, issue.url_id, occurrence)
        if snapshot is not None:
            pages.append(
                _inspection_page(
                    db,
                    snapshot_id=snapshot.id,
                    targets=[
                        {
                            "kind": "missing",
                            "element_type": missing_type,
                            "label": f"Ontbrekend element: {missing_type}",
                            "location_id": None,
                            "target_url": None,
                            "visible_text": None,
                            "html_fragment": None,
                            "locator": None,
                        }
                    ],
                    occurrence=occurrence,
                )
            )

    if any(target["kind"] == "located" for page in pages for target in page["targets"]):
        availability = "available"
        reason = "exact_location"
    elif pages:
        availability = "limited"
        reason = "element_absent"
    else:
        availability = "unavailable"
        reason = "no_element_evidence"
    return {
        "issue_id": issue.id,
        "website_id": issue.website_id,
        "mode": "historical",
        "availability": availability,
        "reason": reason,
        "pages": pages,
        "live_recheck_available": False,
    }


def _located_target(
    location: ElementLocation, payload: dict[str, object]
) -> dict[str, object]:
    return {
        "kind": "located",
        "element_type": location.element_type,
        "label": location.visible_text or location.element_type,
        "location_id": location.id,
        "target_url": location.target_url,
        "visible_text": location.visible_text,
        "html_fragment": location.html_fragment,
        "locator": _best_locator(location),
        "jump_url": payload.get("jump_url"),
    }


def _best_locator(location: ElementLocation) -> dict[str, object] | None:
    if location.element_id:
        return {"strategy": "id", "value": location.element_id, "reliable": True}
    if location.css_selector:
        return {"strategy": "css", "value": location.css_selector, "reliable": True}
    if location.xpath:
        return {"strategy": "xpath", "value": location.xpath, "reliable": False}
    if location.text_is_unique and location.visible_text:
        return {"strategy": "text", "value": location.visible_text, "reliable": True}
    return None


def _inspection_page(
    db: Session,
    *,
    snapshot_id: UUID,
    targets: list[dict[str, object]],
    occurrence: IssueOccurrence | None,
) -> dict[str, object]:
    snapshot = db.get(UrlSnapshot, snapshot_id)
    if snapshot is None:
        raise RuntimeError("Inspection snapshot no longer exists")
    url = db.get(Url, snapshot.url_id)
    render = db.scalar(
        select(RenderObservation).where(RenderObservation.source_snapshot_id == snapshot.id)
    )
    return {
        "url_id": snapshot.url_id,
        "source_url": url.normalized_url if url else snapshot.requested_url,
        "snapshot_id": snapshot.id,
        "crawl_run_id": snapshot.crawl_run_id,
        "captured_at": snapshot.checked_at,
        "is_current_occurrence": bool(
            occurrence
            and (
                occurrence.snapshot_id == snapshot.id
                or occurrence.crawl_run_id == snapshot.crawl_run_id
            )
        ),
        "render_status": render.status if render else "not_rendered",
        "rendered_at": render.rendered_at if render else None,
        "targets": targets,
    }


def _issue_snapshot(
    db: Session, url_id: UUID, occurrence: IssueOccurrence | None
) -> UrlSnapshot | None:
    if occurrence and occurrence.snapshot_id:
        snapshot = db.get(UrlSnapshot, occurrence.snapshot_id)
        if snapshot and snapshot.url_id == url_id:
            return snapshot
    return db.scalar(
        select(UrlSnapshot)
        .where(UrlSnapshot.url_id == url_id)
        .order_by(UrlSnapshot.checked_at.desc())
        .limit(1)
    )

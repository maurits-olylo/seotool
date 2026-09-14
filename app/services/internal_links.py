"""Internal link rankings from a single completed full crawl."""

from datetime import UTC, timedelta
from typing import Any
from urllib.parse import unquote, urlsplit
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.models.common import utc_now
from app.models.crawl import CrawlRun, UrlLink, UrlSnapshot
from app.models.discovery import Url
from app.services.retention_policy import POLICIES


def completed_runs(db: Session, website_id: UUID) -> list[CrawlRun]:
    return list(
        db.scalars(
            select(CrawlRun)
            .where(
                CrawlRun.website_id == website_id,
                CrawlRun.crawl_type == "full_site_crawl",
                CrawlRun.status.in_(("succeeded", "partially_succeeded")),
                CrawlRun.finished_at.is_not(None),
            )
            .order_by(CrawlRun.finished_at.desc(), CrawlRun.id.desc())
            .limit(2)
        )
    )


def link_counts(db: Session, run: CrawlRun) -> dict[UUID, int]:
    source = aliased(Url)
    target = aliased(Url)
    return dict(
        db.execute(
            select(
                UrlLink.target_url_id,
                func.count(func.distinct(UrlLink.source_url_id)),
            )
            .join(source, source.id == UrlLink.source_url_id)
            .join(target, target.id == UrlLink.target_url_id)
            .where(
                UrlLink.crawl_run_id == run.id,
                UrlLink.is_internal.is_(True),
                source.website_id == run.website_id,
                target.website_id == run.website_id,
                source.id != target.id,
            )
            .group_by(UrlLink.target_url_id)
        ).all()
    )


def snapshot_statuses(db: Session, run: CrawlRun) -> dict[UUID, int | None]:
    # A retry can produce more than one snapshot. Keep the last measurement in this run.
    return dict(
        db.execute(
            select(UrlSnapshot.url_id, UrlSnapshot.status_code)
            .join(Url, Url.id == UrlSnapshot.url_id)
            .where(UrlSnapshot.crawl_run_id == run.id, Url.website_id == run.website_id)
            .order_by(UrlSnapshot.checked_at, UrlSnapshot.id)
        ).all()
    )


def ranking(db: Session, website_id: UUID) -> dict[str, Any]:
    runs = completed_runs(db, website_id)
    if not runs:
        return {
            "crawl_run_id": None,
            "finished_at": None,
            "previous_finished_at": None,
            "items": [],
            "top": [],
        }
    run = runs[0]
    cutoff = utc_now() - timedelta(days=POLICIES["url_links"].retain_days or 180)
    if run.started_at.replace(tzinfo=UTC) < cutoff:
        return {
            "crawl_run_id": None,
            "finished_at": run.finished_at,
            "previous_finished_at": None,
            "items": [],
            "top": [],
            "reason": (
                "Deze crawl valt buiten de bewaartermijn voor linkdetails. "
                "Voer een nieuwe volledige crawl uit."
            ),
        }
    counts = link_counts(db, run)
    statuses = snapshot_statuses(db, run)
    previous = runs[1] if len(runs) > 1 else None
    if previous and previous.started_at.replace(tzinfo=UTC) < cutoff:
        previous = None
    previous_counts = link_counts(db, previous) if previous else {}
    previous_ids = (
        set(snapshot_statuses(db, previous)) | set(previous_counts) if previous else set()
    )
    candidate_ids = set(statuses) | set(counts)
    items = []
    if candidate_ids:
        for url_id, url in db.execute(
            select(Url.id, Url.normalized_url).where(
                Url.website_id == website_id,
                Url.id.in_(candidate_ids),
            )
        ):
            count = counts.get(url_id, 0)
            items.append(
                {
                    "url_id": url_id,
                    "url": url,
                    "incoming_pages": count,
                    "status_code": statuses.get(url_id),
                    "change": count - previous_counts.get(url_id, 0)
                    if url_id in previous_ids
                    and run.status == "succeeded"
                    and previous is not None
                    and previous.status == "succeeded"
                    else None,
                }
            )
    summary = classify_items(items, len(statuses))
    items.sort(key=lambda item: (-item["incoming_pages"], item["url"]))
    return {
        "crawl_status": run.status,
        "failed_urls": run.failed_urls,
        "crawled_urls": run.crawled_urls,
        "comparison_available": bool(previous and previous.status == run.status == "succeeded"),
        "summary": summary,
        "measured_urls": len(statuses),
        "crawl_run_id": run.id,
        "finished_at": run.finished_at,
        "previous_finished_at": previous.finished_at if previous else None,
        "items": items,
        "top": [item for item in items if item["incoming_pages"] > 0][:10],
    }


def referring_pages(
    db: Session,
    run: CrawlRun,
    target_id: UUID,
    offset: int,
    limit: int,
) -> dict[str, Any]:
    query = (
        select(Url.id, Url.normalized_url)
        .join(
            UrlLink,
            UrlLink.source_url_id == Url.id,
        )
        .where(
            Url.website_id == run.website_id,
            UrlLink.crawl_run_id == run.id,
            UrlLink.target_url_id == target_id,
            UrlLink.is_internal.is_(True),
            Url.id != target_id,
        )
        .distinct()
    )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    sources = db.execute(query.order_by(Url.normalized_url).offset(offset).limit(limit)).all()
    source_ids = [row.id for row in sources]
    labels: dict[UUID, set[str]] = {}
    if source_ids:
        for source_id, anchor in db.execute(
            select(UrlLink.source_url_id, UrlLink.anchor_text).where(
                UrlLink.crawl_run_id == run.id,
                UrlLink.target_url_id == target_id,
                UrlLink.is_internal.is_(True),
                UrlLink.source_url_id.in_(source_ids),
            )
        ):
            labels.setdefault(source_id, set()).add(anchor or "")
    return {
        "total": total,
        "items": [
            {"url": row.normalized_url, "anchor_texts": sorted(labels.get(row.id, set()))}
            for row in sources
        ],
    }


def classify_items(items: list[dict[str, Any]], measured_urls: int) -> dict[str, int]:
    """Label review candidates, never infer DOM position from frequency."""
    summary = dict.fromkeys(("attention", "low", "lost", "errors", "repeated", "technical"), 0)
    for item in items:
        path = unquote(urlsplit(item["url"]).path).lower().rstrip("/")
        technical = (
            any(
                path == prefix or path.startswith(prefix + "/")
                for prefix in ("/admin-panel", "/wp-admin", "/wp-json", "/cdn-cgi", "/api")
            )
            or path == "/wp-login.php"
        )
        count = item["incoming_pages"]
        status = item["status_code"]
        flags = {
            "technical": technical,
            "repeated": measured_urls >= 10 and count / measured_urls >= 0.8,
            "low": not technical and status == 200 and count <= 2,
            "lost": (item["change"] or 0) < 0,
            "errors": count > 0 and status is not None and status >= 400,
        }
        flags["attention"] = flags["low"] or flags["lost"] or flags["errors"]
        item["signals"] = [key for key, value in flags.items() if value]
        for key, value in flags.items():
            summary[key] += int(value)
    return summary

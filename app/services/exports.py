import csv
import uuid
from datetime import UTC, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.worksheet.table import Table, TableStyleInfo
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.crawl import CrawlRun, UrlLink
from app.models.discovery import Url
from app.models.exports import Export
from app.models.issues import Change, Issue
from app.models.website import Website

EXPORT_ROOT = Path("/app/exports")


def generate_export(export_id: str) -> None:
    with SessionLocal() as db:
        export = db.get(Export, uuid.UUID(export_id))
        if export is None or export.status != "pending":
            return
        export.status = "running"
        db.commit()
        try:
            EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
            suffix = "xlsx" if export.export_type == "excel" else "csv"
            path = EXPORT_ROOT / f"{export.id}.{suffix}"
            if export.export_type == "excel":
                _write_excel(db, export.website_id, path)
            else:
                _write_csv(db, export.website_id, export.export_type, path)
            export.file_path = str(path)
            export.status = "succeeded"
            export.finished_at = datetime.now(UTC)
            db.commit()
        except Exception as exc:
            db.rollback()
            export = db.get(Export, uuid.UUID(export_id))
            if export:
                export.status = "failed"
                export.error_message = str(exc)[:4000]
                export.finished_at = datetime.now(UTC)
                db.commit()
            raise


def _datasets(db: Session, website_id: object) -> dict[str, tuple[list[str], list[list[object]]]]:
    urls = list(db.scalars(select(Url).where(Url.website_id == website_id)))
    url_ids = [url.id for url in urls]
    url_by_id = {url.id: url.normalized_url for url in urls}
    issues = list(db.scalars(select(Issue).where(Issue.website_id == website_id)))
    changes = list(db.scalars(select(Change).where(Change.website_id == website_id)))
    latest_full_run_id = db.scalar(
        select(CrawlRun.id)
        .where(
            CrawlRun.website_id == website_id,
            CrawlRun.crawl_type == "full_site_crawl",
            CrawlRun.status == "succeeded",
        )
        .order_by(CrawlRun.finished_at.desc())
        .limit(1)
    )
    links = (
        list(
            db.execute(
                select(
                    UrlLink.source_url_id,
                    UrlLink.target_url_id,
                    UrlLink.target_url,
                    UrlLink.anchor_text,
                    UrlLink.is_internal,
                    UrlLink.is_nofollow,
                    UrlLink.http_status,
                )
                .distinct()
                .where(
                    UrlLink.source_url_id.in_(url_ids),
                    UrlLink.crawl_run_id == latest_full_run_id,
                )
            )
        )
        if url_ids and latest_full_run_id
        else []
    )
    return {
        "urls": (
            [
                "url",
                "status_code",
                "is_active",
                "is_indexable",
                "first_seen_at",
                "last_seen_at",
            ],
            [
                [
                    url.normalized_url,
                    url.current_status_code,
                    url.is_active,
                    url.is_indexable,
                    url.first_seen_at,
                    url.last_seen_at,
                ]
                for url in urls
            ],
        ),
        "issues": (
            [
                "url",
                "type",
                "category",
                "severity",
                "status",
                "title",
                "first_detected",
                "last_detected",
            ],
            [
                [
                    url_by_id.get(issue.url_id),
                    issue.issue_type,
                    issue.category,
                    issue.severity,
                    issue.status,
                    issue.title,
                    issue.first_detected_at,
                    issue.last_detected_at,
                ]
                for issue in issues
            ],
        ),
        "changes": (
            ["url", "type", "field", "old_value", "new_value", "detected_at"],
            [
                [
                    url_by_id.get(change.url_id),
                    change.change_type,
                    change.field_name,
                    change.old_value,
                    change.new_value,
                    change.detected_at,
                ]
                for change in changes
            ],
        ),
        "links": (
            [
                "source_url",
                "target_url",
                "anchor_text",
                "internal",
                "nofollow",
                "status",
            ],
            [
                [
                    url_by_id.get(link.source_url_id),
                    link.target_url,
                    link.anchor_text,
                    link.is_internal,
                    link.is_nofollow,
                    link.http_status,
                ]
                for link in links
            ],
        ),
    }


def _write_csv(db: Session, website_id: object, export_type: str, path: Path) -> None:
    datasets = _datasets(db, website_id)
    key = "issues" if export_type == "technical" else export_type
    if key not in datasets:
        raise ValueError("Unsupported CSV export type")
    headers, rows = datasets[key]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def _write_excel(db: Session, website_id: object, path: Path) -> None:
    website = db.get(Website, website_id)
    workbook = Workbook()
    metadata = workbook.active
    metadata.title = "Metadata"
    metadata.append(["Website", website.name if website else str(website_id)])
    metadata.append(["Exported at", datetime.now(UTC).isoformat()])
    for name, (headers, rows) in _datasets(db, website_id).items():
        sheet = workbook.create_sheet(name.title())
        sheet.append(headers)
        for row in rows:
            sheet.append([_excel_value(value) for value in row])
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        if rows:
            table = Table(displayName=f"Table{name.title()}", ref=sheet.dimensions)
            table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
            sheet.add_table(table)
    workbook.save(path)


def _excel_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.astimezone(UTC).replace(tzinfo=None)
    if isinstance(value, uuid.UUID):
        return str(value)
    return value

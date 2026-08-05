from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.queue import enqueue_export, queue_has_capacity
from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.models.exports import Export
from app.models.website import Website
from app.schemas.exports import ExportCreate, ExportRead
from app.services.authorization import require_website_access, require_write_access

router = APIRouter(prefix="/exports", tags=["exports"])


@router.post("", response_model=ExportRead, status_code=201)
def create_export(
    payload: ExportCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> Export:
    website = require_website_access(db, principal, payload.website_id)
    require_write_access(db, principal, website.client_id)
    if get_settings().app_env != "test" and not queue_has_capacity("exports"):
        raise HTTPException(status_code=503, detail="De exportwachtrij is tijdelijk vol")
    existing = db.scalar(
        select(Export.id).where(
            Export.website_id == payload.website_id,
            or_(
                Export.status.in_(["pending", "running"]),
                and_(Export.status == "succeeded", Export.downloaded_at.is_(None)),
            ),
        )
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Er staat al een export klaar of in de wachtrij",
        )
    data = payload.model_dump()
    data["item_ids"] = (
        [str(item_id) for item_id in payload.item_ids] if payload.item_ids is not None else None
    )
    export = Export(**data)
    db.add(export)
    db.commit()
    db.refresh(export)
    if get_settings().app_env != "test":
        queued = enqueue_export(str(export.id), website_id=str(export.website_id))
        if not queued:
            export.status = "failed"
            export.error_message = "De exportwachtrij is tijdelijk vol"
            db.commit()
            raise HTTPException(status_code=503, detail=export.error_message)
    return export


@router.get("", response_model=list[ExportRead])
def list_exports(
    website_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> list[Export]:
    require_website_access(db, principal, website_id)
    return list(
        db.scalars(
            select(Export)
            .where(Export.website_id == website_id)
            .order_by(Export.created_at.desc())
            .limit(limit)
        )
    )


@router.get("/{export_id}", response_model=ExportRead)
def get_export(
    export_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> Export:
    export = db.get(Export, export_id)
    if not export:
        raise HTTPException(status_code=404, detail="Export not found")
    require_website_access(db, principal, export.website_id)
    return export


@router.get("/{export_id}/download")
def download_export(
    export_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> FileResponse:
    export = db.get(Export, export_id)
    if not export or export.status != "succeeded" or not export.file_path:
        raise HTTPException(status_code=404, detail="Export is not ready")
    require_website_access(db, principal, export.website_id)
    path = Path(export.file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Export file is missing")
    export.downloaded_at = datetime.now(UTC)
    db.commit()
    website = db.get(Website, export.website_id)
    website_name = website.name if website else "Website"
    export_date = (export.finished_at or export.created_at).date().isoformat()
    labels = {
        "excel": "Issuelijst",
        "urls": "URLs",
        "changes": "Wijzigingen",
        "vacancies": "Vacatures",
        "tasks": "Taken",
    }
    label = labels.get(export.export_type, export.export_type.title())
    filename = f"Export {label} - {website_name} - {export_date} - SEOMonitor{path.suffix}"
    return FileResponse(path, filename=filename)

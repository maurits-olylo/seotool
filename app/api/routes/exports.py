from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.queue import get_queue
from app.db.session import get_db
from app.models.exports import Export
from app.models.website import Website
from app.schemas.exports import ExportCreate, ExportRead

router = APIRouter(prefix="/exports", tags=["exports"])


@router.post("", response_model=ExportRead, status_code=201)
def create_export(payload: ExportCreate, db: Session = Depends(get_db)) -> Export:
    if not db.get(Website, payload.website_id):
        raise HTTPException(status_code=404, detail="Website not found")
    export = Export(**payload.model_dump())
    db.add(export)
    db.commit()
    db.refresh(export)
    if get_settings().app_env != "test":
        get_queue().enqueue("app.services.exports.generate_export", str(export.id))
    return export


@router.get("/{export_id}", response_model=ExportRead)
def get_export(export_id: UUID, db: Session = Depends(get_db)) -> Export:
    export = db.get(Export, export_id)
    if not export:
        raise HTTPException(status_code=404, detail="Export not found")
    return export


@router.get("/{export_id}/download")
def download_export(export_id: UUID, db: Session = Depends(get_db)) -> FileResponse:
    export = db.get(Export, export_id)
    if not export or export.status != "succeeded" or not export.file_path:
        raise HTTPException(status_code=404, detail="Export is not ready")
    path = Path(export.file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Export file is missing")
    return FileResponse(path, filename=path.name)

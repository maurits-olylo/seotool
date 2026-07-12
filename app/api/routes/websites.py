from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.models.client import Client
from app.models.website import Website, WebsiteSettings
from app.schemas.website import WebsiteCreate, WebsiteRead, WebsiteSettingsData, WebsiteUpdate
from app.services.authorization import accessible_client_ids, require_client_access

router = APIRouter(prefix="/websites", tags=["websites"])


def website_or_404(website_id: UUID, db: Session) -> Website:
    website = db.get(Website, website_id)
    if not website:
        raise HTTPException(status_code=404, detail="Website not found")
    return website


@router.post("", response_model=WebsiteRead, status_code=201)
def create_website(
    payload: WebsiteCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> Website:
    require_client_access(db, principal, payload.client_id, admin=True)
    if not db.get(Client, payload.client_id):
        raise HTTPException(status_code=404, detail="Client not found")
    data = payload.model_dump()
    data["base_url"] = str(data["base_url"])
    website = Website(**data)
    website.settings = WebsiteSettings()
    db.add(website)
    db.commit()
    db.refresh(website)
    return website


@router.get("", response_model=list[WebsiteRead])
def list_websites(
    client_id: UUID | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> list[Website]:
    query = select(Website).order_by(Website.name)
    if client_id:
        require_client_access(db, principal, client_id)
        query = query.where(Website.client_id == client_id)
    else:
        client_ids = accessible_client_ids(db, principal)
        if client_ids is not None:
            query = query.where(Website.client_id.in_(client_ids))
    return list(db.scalars(query))


@router.get("/{website_id}", response_model=WebsiteRead)
def get_website(
    website_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> Website:
    website = website_or_404(website_id, db)
    require_client_access(db, principal, website.client_id)
    return website


@router.patch("/{website_id}", response_model=WebsiteRead)
def update_website(
    website_id: UUID,
    payload: WebsiteUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> Website:
    website = website_or_404(website_id, db)
    require_client_access(db, principal, website.client_id, admin=True)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(website, key, str(value) if key == "base_url" else value)
    db.commit()
    db.refresh(website)
    return website


@router.delete("/{website_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_website(
    website_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> Response:
    website = website_or_404(website_id, db)
    require_client_access(db, principal, website.client_id, admin=True)
    db.delete(website)
    db.commit()
    return Response(status_code=204)


@router.get("/{website_id}/settings", response_model=WebsiteSettingsData)
def get_settings(
    website_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> WebsiteSettings:
    website = website_or_404(website_id, db)
    require_client_access(db, principal, website.client_id)
    return website.settings


@router.put("/{website_id}/settings", response_model=WebsiteSettingsData)
def update_settings(
    website_id: UUID,
    payload: WebsiteSettingsData,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> WebsiteSettings:
    website = website_or_404(website_id, db)
    require_client_access(db, principal, website.client_id, admin=True)
    settings = website.settings or WebsiteSettings(website_id=website.id)
    for key, value in payload.model_dump(exclude={"website_id"}).items():
        setattr(settings, key, value)
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.client import Client
from app.models.integrations import IntegrationConnection, WebsiteIntegration
from app.models.website import Website
from app.schemas.integrations import (
    IntegrationConnectionCreate,
    IntegrationConnectionRead,
    WebsiteIntegrationCreate,
    WebsiteIntegrationRead,
)

router = APIRouter(tags=["integrations"])


@router.get(
    "/clients/{client_id}/integrations", response_model=list[IntegrationConnectionRead]
)
def list_client_integrations(
    client_id: UUID, db: Session = Depends(get_db)
) -> list[IntegrationConnection]:
    if not db.get(Client, client_id):
        raise HTTPException(status_code=404, detail="Client not found")
    return list(
        db.scalars(
            select(IntegrationConnection)
            .where(IntegrationConnection.client_id == client_id)
            .order_by(IntegrationConnection.provider)
        )
    )


@router.post(
    "/clients/{client_id}/integrations",
    response_model=IntegrationConnectionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_client_integration(
    client_id: UUID,
    payload: IntegrationConnectionCreate,
    db: Session = Depends(get_db),
) -> IntegrationConnection:
    if not db.get(Client, client_id):
        raise HTTPException(status_code=404, detail="Client not found")
    connection = IntegrationConnection(client_id=client_id, **payload.model_dump())
    db.add(connection)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Provider already configured") from exc
    db.refresh(connection)
    return connection


@router.get(
    "/websites/{website_id}/integrations", response_model=list[WebsiteIntegrationRead]
)
def list_website_integrations(
    website_id: UUID, db: Session = Depends(get_db)
) -> list[WebsiteIntegration]:
    if not db.get(Website, website_id):
        raise HTTPException(status_code=404, detail="Website not found")
    return list(
        db.scalars(
            select(WebsiteIntegration)
            .where(WebsiteIntegration.website_id == website_id)
            .order_by(WebsiteIntegration.service)
        )
    )


@router.post(
    "/websites/{website_id}/integrations",
    response_model=WebsiteIntegrationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_website_integration(
    website_id: UUID,
    payload: WebsiteIntegrationCreate,
    db: Session = Depends(get_db),
) -> WebsiteIntegration:
    website = db.get(Website, website_id)
    connection = db.get(IntegrationConnection, payload.connection_id)
    if not website:
        raise HTTPException(status_code=404, detail="Website not found")
    if not connection or connection.client_id != website.client_id:
        raise HTTPException(status_code=422, detail="Connection does not belong to this client")
    expected_provider = "bing" if payload.service == "bing_webmaster" else "google"
    if connection.provider != expected_provider:
        raise HTTPException(status_code=422, detail="Service and provider do not match")
    mapping = WebsiteIntegration(website_id=website_id, **payload.model_dump())
    db.add(mapping)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Service already mapped") from exc
    db.refresh(mapping)
    return mapping

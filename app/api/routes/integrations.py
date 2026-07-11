from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.client import Client
from app.models.integrations import IntegrationConnection, WebsiteIntegration
from app.models.website import Website
from app.schemas.integrations import (
    GooglePropertiesRead,
    IntegrationConnectionCreate,
    IntegrationConnectionRead,
    WebsiteIntegrationCreate,
    WebsiteIntegrationRead,
    WebsiteIntegrationUpsert,
)
from app.services.google_integrations import list_google_properties
from app.services.oauth import (
    GOOGLE_SCOPES,
    encrypt_token,
    google_authorization_url,
    google_is_configured,
    parse_oauth_state,
)

router = APIRouter(tags=["integrations"])
oauth_router = APIRouter(tags=["integrations"])


@router.get("/integrations/google/config")
def google_config() -> dict[str, bool]:
    return {"configured": google_is_configured()}


@router.get("/integrations/google/authorize")
def authorize_google(
    client_id: UUID = Query(), db: Session = Depends(get_db)
) -> RedirectResponse:
    if not google_is_configured():
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    if not db.get(Client, client_id):
        raise HTTPException(status_code=404, detail="Client not found")
    return RedirectResponse(google_authorization_url(client_id), status_code=302)


@oauth_router.get("/integrations/google/callback", include_in_schema=False)
async def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if error or not code or not state or not google_is_configured():
        return RedirectResponse("/?integration=google-error", status_code=302)
    try:
        client_id = parse_oauth_state(state)
    except ValueError:
        return RedirectResponse("/?integration=google-error", status_code=302)
    if not db.get(Client, client_id):
        return RedirectResponse("/?integration=google-error", status_code=302)

    settings = get_settings()
    async with httpx.AsyncClient(timeout=20) as http:
        token_response = await http.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.google_redirect_uri,
            },
        )
        if token_response.status_code != 200:
            return RedirectResponse("/?integration=google-error", status_code=302)
        token_data = token_response.json()
        user_response = await http.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        if user_response.status_code != 200:
            return RedirectResponse("/?integration=google-error", status_code=302)
        account_email = user_response.json().get("email")

    connection = db.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.client_id == client_id,
            IntegrationConnection.provider == "google",
        )
    )
    if connection is None:
        connection = IntegrationConnection(client_id=client_id, provider="google")
        db.add(connection)
    connection.account_email = account_email
    connection.status = "connected"
    connection.encrypted_access_token = encrypt_token(token_data.get("access_token"))
    refresh_token = token_data.get("refresh_token")
    if refresh_token:
        connection.encrypted_refresh_token = encrypt_token(refresh_token)
    connection.token_expires_at = datetime.now(UTC) + timedelta(
        seconds=int(token_data.get("expires_in", 3600))
    )
    connection.scopes = token_data.get("scope", " ".join(GOOGLE_SCOPES)).split()
    connection.last_error = None
    db.commit()
    return RedirectResponse("/?integration=google-connected", status_code=302)


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
    "/clients/{client_id}/integrations/google/properties",
    response_model=GooglePropertiesRead,
)
async def google_properties(
    client_id: UUID, db: Session = Depends(get_db)
) -> dict[str, list[dict[str, str]]]:
    connection = db.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.client_id == client_id,
            IntegrationConnection.provider == "google",
            IntegrationConnection.status == "connected",
        )
    )
    if not connection:
        raise HTTPException(status_code=409, detail="Google account is not connected")
    try:
        return await list_google_properties(db, connection)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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


@router.put(
    "/websites/{website_id}/integrations/{service}",
    response_model=WebsiteIntegrationRead,
)
def upsert_website_integration(
    website_id: UUID,
    service: str,
    payload: WebsiteIntegrationUpsert,
    db: Session = Depends(get_db),
) -> WebsiteIntegration:
    if service not in {"search_console", "ga4", "bing_webmaster"}:
        raise HTTPException(status_code=422, detail="Unsupported integration service")
    website = db.get(Website, website_id)
    connection = db.get(IntegrationConnection, payload.connection_id)
    if not website:
        raise HTTPException(status_code=404, detail="Website not found")
    if not connection or connection.client_id != website.client_id:
        raise HTTPException(status_code=422, detail="Connection does not belong to this client")
    expected_provider = "bing" if service == "bing_webmaster" else "google"
    if connection.provider != expected_provider:
        raise HTTPException(status_code=422, detail="Service and provider do not match")
    mapping = db.scalar(
        select(WebsiteIntegration).where(
            WebsiteIntegration.website_id == website_id,
            WebsiteIntegration.service == service,
        )
    )
    if mapping is None:
        mapping = WebsiteIntegration(
            website_id=website_id,
            service=service,
            connection_id=payload.connection_id,
            external_property_id=payload.external_property_id,
            external_property_name=payload.external_property_name,
        )
        db.add(mapping)
    else:
        mapping.connection_id = payload.connection_id
        mapping.external_property_id = payload.external_property_id
        mapping.external_property_name = payload.external_property_name
        mapping.status = "active"
    db.commit()
    db.refresh(mapping)
    return mapping

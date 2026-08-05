import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.queue import (
    INTEGRATION_QUEUE,
    PERFORMANCE_QUEUE,
    enqueue_integration_sync,
    enqueue_performance_sync,
    queue_has_capacity,
)
from app.core.security import Principal, active_session_id, require_api_key
from app.db.session import get_db
from app.models.client import Client
from app.models.integrations import (
    BingPageMetric,
    GoogleAnalyticsEventMetric,
    GoogleAnalyticsMetric,
    IntegrationConnection,
    SearchConsoleMetric,
    SearchConsoleQueryMetric,
    UrlInspectionResult,
    WebsiteIntegration,
)
from app.models.performance import PerformanceObservation
from app.models.website import Website, WebsiteSettings
from app.schemas.integrations import (
    BingBacklinkCsvImport,
    BingPropertiesRead,
    GoogleAnalyticsKeyEventRead,
    GoogleAnalyticsKeyEventSelection,
    GooglePropertiesRead,
    IntegrationConnectionCreate,
    IntegrationConnectionRead,
    MatomoConnectionCreate,
    MatomoSitesRead,
    PerformanceObservationRead,
    PrimaryAnalyticsSourceUpdate,
    UrlInspectionResultRead,
    WebsiteIntegrationCreate,
    WebsiteIntegrationRead,
    WebsiteIntegrationUpsert,
)
from app.services.authorization import require_client_access, require_website_access
from app.services.bing_backlink_import import (
    InvalidBingBacklinkExport,
    import_bing_backlink_exports,
)
from app.services.bing_integrations import BING_TOKEN_URL, list_bing_sites, sync_bing_webmaster
from app.services.google_analytics import sync_google_analytics
from app.services.google_integrations import list_google_properties
from app.services.matomo import (
    list_connection_sites,
    list_matomo_sites,
    normalize_matomo_server_url,
    sync_matomo,
)
from app.services.oauth import (
    BING_SCOPES,
    GOOGLE_SCOPES,
    bing_authorization_url,
    bing_is_configured,
    consume_oauth_state,
    create_oauth_state,
    encrypt_token,
    google_authorization_url,
    google_is_configured,
)
from app.services.search_console import sync_search_console
from app.services.url_inspection import sync_url_inspection

router = APIRouter(tags=["integrations"])
oauth_router = APIRouter(tags=["integrations"])


@router.get("/integrations/google/config")
def google_config() -> dict[str, bool]:
    return {"configured": google_is_configured()}


@router.get("/integrations/bing/config")
def bing_config() -> dict[str, bool]:
    return {"configured": bing_is_configured()}


@router.get("/integrations/google/authorize")
def authorize_google(
    client_id: UUID = Query(),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
    seo_session: str | None = Cookie(default=None),
) -> RedirectResponse:
    if not google_is_configured():
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    if not db.get(Client, client_id):
        raise HTTPException(status_code=404, detail="Client not found")
    require_client_access(db, principal, client_id, admin=True)
    session_id = active_session_id(seo_session)
    if not principal.user_id or not session_id:
        raise HTTPException(status_code=403, detail="Een persoonlijke sessie is vereist")
    state = create_oauth_state(db, client_id, principal.user_id, session_id, "google")
    return RedirectResponse(google_authorization_url(state), status_code=302)


@router.get("/integrations/bing/authorize")
def authorize_bing(
    client_id: UUID = Query(),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
    seo_session: str | None = Cookie(default=None),
) -> RedirectResponse:
    if not bing_is_configured():
        raise HTTPException(status_code=503, detail="Bing OAuth is not configured")
    if not db.get(Client, client_id):
        raise HTTPException(status_code=404, detail="Client not found")
    require_client_access(db, principal, client_id, admin=True)
    session_id = active_session_id(seo_session)
    if not principal.user_id or not session_id:
        raise HTTPException(status_code=403, detail="Een persoonlijke sessie is vereist")
    state = create_oauth_state(db, client_id, principal.user_id, session_id, "bing")
    return RedirectResponse(bing_authorization_url(state), status_code=302)


@oauth_router.get("/integrations/google/callback", include_in_schema=False)
async def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
    seo_session: str | None = Cookie(default=None),
) -> RedirectResponse:
    if error or not code or not state or not google_is_configured():
        return RedirectResponse("/app?integration=google-error", status_code=302)
    try:
        session_id = active_session_id(seo_session)
        if not session_id:
            raise ValueError
        client_id = consume_oauth_state(db, state, "google", session_id)
    except ValueError:
        return RedirectResponse("/app?integration=google-error", status_code=302)
    if not db.get(Client, client_id):
        return RedirectResponse("/app?integration=google-error", status_code=302)

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
            return RedirectResponse("/app?integration=google-error", status_code=302)
        token_data = token_response.json()
        user_response = await http.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        if user_response.status_code != 200:
            return RedirectResponse("/app?integration=google-error", status_code=302)
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
    return RedirectResponse("/app?integration=google-connected", status_code=302)


@oauth_router.get("/integrations/bing/callback", include_in_schema=False)
async def bing_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
    seo_session: str | None = Cookie(default=None),
) -> RedirectResponse:
    if error or not code or not state or not bing_is_configured():
        return RedirectResponse("/app?integration=bing-error", status_code=302)
    try:
        session_id = active_session_id(seo_session)
        if not session_id:
            raise ValueError
        client_id = consume_oauth_state(db, state, "bing", session_id)
    except ValueError:
        return RedirectResponse("/app?integration=bing-error", status_code=302)
    if not db.get(Client, client_id):
        return RedirectResponse("/app?integration=bing-error", status_code=302)

    settings = get_settings()
    async with httpx.AsyncClient(timeout=20) as http:
        response = await http.post(
            BING_TOKEN_URL,
            data={
                "client_id": settings.bing_client_id,
                "client_secret": settings.bing_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.bing_redirect_uri,
            },
        )
    if response.status_code != 200:
        return RedirectResponse("/app?integration=bing-error", status_code=302)
    token_data = response.json()
    connection = db.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.client_id == client_id,
            IntegrationConnection.provider == "bing",
        )
    )
    if connection is None:
        connection = IntegrationConnection(client_id=client_id, provider="bing")
        db.add(connection)
    connection.status = "connected"
    connection.encrypted_access_token = encrypt_token(token_data.get("access_token"))
    if token_data.get("refresh_token"):
        connection.encrypted_refresh_token = encrypt_token(token_data["refresh_token"])
    connection.token_expires_at = datetime.now(UTC) + timedelta(
        seconds=int(token_data.get("expires_in", 3600))
    )
    connection.scopes = token_data.get("scope", " ".join(BING_SCOPES)).split()
    connection.last_error = None
    db.commit()
    return RedirectResponse("/app?integration=bing-connected", status_code=302)


@router.get("/clients/{client_id}/integrations", response_model=list[IntegrationConnectionRead])
def list_client_integrations(
    client_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> list[IntegrationConnection]:
    if not db.get(Client, client_id):
        raise HTTPException(status_code=404, detail="Client not found")
    require_client_access(db, principal, client_id, admin=True)
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
    principal: Principal = Depends(require_api_key),
) -> IntegrationConnection:
    if not db.get(Client, client_id):
        raise HTTPException(status_code=404, detail="Client not found")
    require_client_access(db, principal, client_id, admin=True)
    connection = IntegrationConnection(client_id=client_id, **payload.model_dump())
    db.add(connection)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Provider already configured") from exc
    db.refresh(connection)
    return connection


@router.put(
    "/clients/{client_id}/integrations/matomo",
    response_model=MatomoSitesRead,
)
async def connect_matomo(
    client_id: UUID,
    payload: MatomoConnectionCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    if not db.get(Client, client_id):
        raise HTTPException(status_code=404, detail="Client not found")
    require_client_access(db, principal, client_id, admin=True)
    try:
        server_url = normalize_matomo_server_url(payload.server_url)
        sites = await list_matomo_sites(server_url, payload.token_auth)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    connection = db.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.client_id == client_id,
            IntegrationConnection.provider == "matomo",
        )
    )
    if connection is None:
        connection = IntegrationConnection(client_id=client_id, provider="matomo")
        db.add(connection)
    connection.status = "connected"
    connection.encrypted_access_token = encrypt_token(payload.token_auth)
    connection.encrypted_refresh_token = None
    connection.token_expires_at = None
    connection.scopes = ["analytics:read"]
    connection.settings = {"server_url": server_url}
    connection.last_error = None
    db.commit()
    return {"sites": sites}


@router.get(
    "/clients/{client_id}/integrations/matomo/sites",
    response_model=MatomoSitesRead,
)
async def matomo_sites(
    client_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    require_client_access(db, principal, client_id, admin=True)
    connection = db.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.client_id == client_id,
            IntegrationConnection.provider == "matomo",
            IntegrationConnection.status == "connected",
        )
    )
    if not connection:
        raise HTTPException(status_code=409, detail="Matomo is not connected")
    try:
        return {"sites": await list_connection_sites(connection)}
    except ValueError as exc:
        connection.status = "error"
        connection.last_error = str(exc)
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get(
    "/clients/{client_id}/integrations/google/properties",
    response_model=GooglePropertiesRead,
)
async def google_properties(
    client_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, list[dict[str, str]]]:
    require_client_access(db, principal, client_id, admin=True)
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
    "/clients/{client_id}/integrations/bing/properties",
    response_model=BingPropertiesRead,
)
async def bing_properties(
    client_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, list[dict[str, str | bool]]]:
    require_client_access(db, principal, client_id, admin=True)
    connection = db.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.client_id == client_id,
            IntegrationConnection.provider == "bing",
            IntegrationConnection.status == "connected",
        )
    )
    if not connection:
        raise HTTPException(status_code=409, detail="Bing account is not connected")
    try:
        return {"sites": await list_bing_sites(db, connection)}
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/websites/{website_id}/integrations", response_model=list[WebsiteIntegrationRead])
def list_website_integrations(
    website_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> list[WebsiteIntegration]:
    require_website_access(db, principal, website_id, admin=True)
    return list(
        db.scalars(
            select(WebsiteIntegration)
            .where(WebsiteIntegration.website_id == website_id)
            .order_by(WebsiteIntegration.service)
        )
    )


@router.put("/websites/{website_id}/integrations/analytics-primary")
def update_primary_analytics_source(
    website_id: UUID,
    payload: PrimaryAnalyticsSourceUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, str]:
    require_website_access(db, principal, website_id, admin=True)
    mapping = db.scalar(
        select(WebsiteIntegration).where(
            WebsiteIntegration.website_id == website_id,
            WebsiteIntegration.service == payload.source,
            WebsiteIntegration.status == "active",
        )
    )
    if not mapping:
        raise HTTPException(status_code=409, detail="Selected analytics source is not active")
    settings = db.get(WebsiteSettings, website_id)
    if not settings:
        raise HTTPException(status_code=404, detail="Website settings not found")
    settings.primary_analytics_source = payload.source
    db.commit()
    return {"source": payload.source}


@router.get("/websites/{website_id}/integrations/analytics-primary")
def get_primary_analytics_source(
    website_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, str | None]:
    require_website_access(db, principal, website_id, admin=True)
    settings = db.get(WebsiteSettings, website_id)
    if not settings:
        raise HTTPException(status_code=404, detail="Website settings not found")
    return {"source": settings.primary_analytics_source}


@router.post(
    "/websites/{website_id}/integrations",
    response_model=WebsiteIntegrationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_website_integration(
    website_id: UUID,
    payload: WebsiteIntegrationCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> WebsiteIntegration:
    website = db.get(Website, website_id)
    connection = db.get(IntegrationConnection, payload.connection_id)
    if not website:
        raise HTTPException(status_code=404, detail="Website not found")
    require_client_access(db, principal, website.client_id, admin=True)
    if not connection or connection.client_id != website.client_id:
        raise HTTPException(status_code=422, detail="Connection does not belong to this client")
    expected_provider = (
        "bing"
        if payload.service == "bing_webmaster"
        else "matomo"
        if payload.service == "matomo"
        else "google"
    )
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
    principal: Principal = Depends(require_api_key),
) -> WebsiteIntegration:
    if service not in {"search_console", "ga4", "bing_webmaster", "matomo"}:
        raise HTTPException(status_code=422, detail="Unsupported integration service")
    website = db.get(Website, website_id)
    connection = db.get(IntegrationConnection, payload.connection_id)
    if not website:
        raise HTTPException(status_code=404, detail="Website not found")
    require_client_access(db, principal, website.client_id, admin=True)
    if not connection or connection.client_id != website.client_id:
        raise HTTPException(status_code=422, detail="Connection does not belong to this client")
    expected_provider = (
        "bing" if service == "bing_webmaster" else service if service == "matomo" else "google"
    )
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


@router.get(
    "/websites/{website_id}/integrations/ga4/key-events",
    response_model=list[GoogleAnalyticsKeyEventRead],
)
def list_google_analytics_key_events(
    website_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> list[dict[str, object]]:
    require_website_access(db, principal, website_id, admin=True)
    mapping = db.scalar(
        select(WebsiteIntegration).where(
            WebsiteIntegration.website_id == website_id,
            WebsiteIntegration.service == "ga4",
        )
    )
    selected = set(mapping.settings.get("qualified_key_events", [])) if mapping else set()
    rows = db.execute(
        select(
            GoogleAnalyticsEventMetric.event_name,
            func.sum(GoogleAnalyticsEventMetric.key_events),
        )
        .where(GoogleAnalyticsEventMetric.website_id == website_id)
        .group_by(GoogleAnalyticsEventMetric.event_name)
        .order_by(func.sum(GoogleAnalyticsEventMetric.key_events).desc())
    )
    return [
        {"event_name": name, "key_events": float(total or 0), "selected": name in selected}
        for name, total in rows
    ]


@router.put(
    "/websites/{website_id}/integrations/ga4/key-events",
    response_model=list[GoogleAnalyticsKeyEventRead],
)
def update_google_analytics_key_events(
    website_id: UUID,
    payload: GoogleAnalyticsKeyEventSelection,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> list[dict[str, object]]:
    require_website_access(db, principal, website_id, admin=True)
    mapping = db.scalar(
        select(WebsiteIntegration).where(
            WebsiteIntegration.website_id == website_id,
            WebsiteIntegration.service == "ga4",
        )
    )
    if not mapping:
        raise HTTPException(status_code=404, detail="GA4 property is not mapped")
    selected = sorted({name.strip() for name in payload.event_names if name.strip()})
    mapping.settings = {**mapping.settings, "qualified_key_events": selected}
    db.commit()
    return list_google_analytics_key_events(website_id, db, principal)


@router.post(
    "/websites/{website_id}/integrations/history-sync",
    status_code=status.HTTP_202_ACCEPTED,
)
def synchronize_integration_history(
    website_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, str | int]:
    require_website_access(db, principal, website_id, admin=True)
    if not queue_has_capacity(INTEGRATION_QUEUE):
        raise HTTPException(status_code=503, detail="De integratiewachtrij is tijdelijk vol")
    now = datetime.now(UTC).isoformat()
    mappings = list(
        db.scalars(
            select(WebsiteIntegration).where(
                WebsiteIntegration.website_id == website_id,
                WebsiteIntegration.service.in_(
                    ["search_console", "ga4", "bing_webmaster", "matomo"]
                ),
            )
        )
    )
    for mapping in mappings:
        mapping.settings = {
            **mapping.settings,
            "history_sync": {
                "status": "queued",
                "days": 480,
                "queued_at": now,
                "updated_at": now,
                "error": None,
            },
        }
    db.commit()
    enqueue_integration_sync(
        str(website_id),
        480,
        job_id=f"integration-history-{website_id}-{uuid.uuid4()}",
    )
    return {"status": "queued", "days": 480}


@router.get("/websites/{website_id}/integrations/history-sync")
def integration_history_status(
    website_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    """Return durable import state plus the imported data-source date ranges."""
    require_website_access(db, principal, website_id, admin=True)
    mappings = list(
        db.scalars(
            select(WebsiteIntegration).where(
                WebsiteIntegration.website_id == website_id,
                WebsiteIntegration.service.in_(
                    ["search_console", "ga4", "bing_webmaster", "matomo"]
                ),
            )
        )
    )
    sync = next(
        (
            mapping.settings.get("history_sync", {})
            for mapping in mappings
            if mapping.settings.get("history_sync")
        ),
        {},
    )
    return {
        "status": sync.get("status", "not_started"),
        "days": sync.get("days"),
        "queued_at": sync.get("queued_at"),
        "updated_at": sync.get("updated_at"),
        "completed_at": sync.get("completed_at"),
        "error": sync.get("error"),
        "coverage": {
            "gsc_from": db.scalar(
                select(func.min(SearchConsoleMetric.date)).where(
                    SearchConsoleMetric.website_id == website_id
                )
            ),
            "gsc_through": db.scalar(
                select(func.max(SearchConsoleMetric.date)).where(
                    SearchConsoleMetric.website_id == website_id
                )
            ),
            "gsc_query_from": db.scalar(
                select(func.min(SearchConsoleQueryMetric.date)).where(
                    SearchConsoleQueryMetric.website_id == website_id
                )
            ),
            "gsc_query_through": db.scalar(
                select(func.max(SearchConsoleQueryMetric.date)).where(
                    SearchConsoleQueryMetric.website_id == website_id
                )
            ),
            "ga4_from": db.scalar(
                select(func.min(GoogleAnalyticsMetric.date)).where(
                    GoogleAnalyticsMetric.website_id == website_id
                )
            ),
            "ga4_through": db.scalar(
                select(func.max(GoogleAnalyticsMetric.date)).where(
                    GoogleAnalyticsMetric.website_id == website_id
                )
            ),
            "bing_from": db.scalar(
                select(func.min(BingPageMetric.date)).where(BingPageMetric.website_id == website_id)
            ),
            "bing_through": db.scalar(
                select(func.max(BingPageMetric.date)).where(BingPageMetric.website_id == website_id)
            ),
        },
    }


@router.post("/websites/{website_id}/integrations/search_console/sync")
async def synchronize_search_console(
    website_id: UUID,
    days: int = Query(default=28, ge=1, le=480),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    require_website_access(db, principal, website_id, admin=True)
    try:
        return await sync_search_console(db, website_id, days)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get(
    "/websites/{website_id}/integrations/url_inspection/results",
    response_model=list[UrlInspectionResultRead],
)
def list_url_inspection_results(
    website_id: UUID,
    url_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> list[UrlInspectionResult]:
    require_website_access(db, principal, website_id)
    query = select(UrlInspectionResult).where(UrlInspectionResult.website_id == website_id)
    if url_id is not None:
        query = query.where(UrlInspectionResult.url_id == url_id)
    return list(db.scalars(query.order_by(UrlInspectionResult.inspected_at.desc()).limit(limit)))


@router.post("/websites/{website_id}/integrations/url_inspection/sync")
async def synchronize_url_inspection(
    website_id: UUID,
    limit: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    require_website_access(db, principal, website_id, admin=True)
    try:
        return await sync_url_inspection(db, website_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get(
    "/websites/{website_id}/integrations/pagespeed/results",
    response_model=list[PerformanceObservationRead],
)
def list_pagespeed_results(
    website_id: UUID,
    url_id: UUID | None = None,
    strategy: str | None = Query(default=None, pattern="^(mobile|desktop)$"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> list[PerformanceObservation]:
    require_website_access(db, principal, website_id)
    query = select(PerformanceObservation).where(PerformanceObservation.website_id == website_id)
    if url_id is not None:
        query = query.where(PerformanceObservation.url_id == url_id)
    if strategy is not None:
        query = query.where(PerformanceObservation.strategy == strategy)
    return list(db.scalars(query.order_by(PerformanceObservation.analyzed_at.desc()).limit(limit)))


@router.post(
    "/websites/{website_id}/integrations/pagespeed/sync",
    status_code=status.HTTP_202_ACCEPTED,
)
def synchronize_pagespeed(
    website_id: UUID,
    strategy: str = Query(default="mobile", pattern="^(mobile|desktop)$"),
    limit: int = Query(default=10, ge=1, le=10),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    require_website_access(db, principal, website_id, admin=True)
    settings = get_settings()
    if not settings.pagespeed_enabled:
        raise HTTPException(status_code=503, detail="PageSpeed is not enabled")
    if not queue_has_capacity(PERFORMANCE_QUEUE):
        raise HTTPException(status_code=503, detail="De performancewachtrij is tijdelijk vol")
    queued = enqueue_performance_sync(
        str(website_id),
        strategy=strategy,
        limit=limit,
        job_id=f"performance-{website_id}-{strategy}-{uuid.uuid4()}",
    )
    if not queued:
        raise HTTPException(status_code=503, detail="De performancewachtrij is tijdelijk vol")
    return {"status": "queued", "strategy": strategy, "limit": limit}


@router.post("/websites/{website_id}/integrations/ga4/sync")
async def synchronize_google_analytics(
    website_id: UUID,
    days: int = Query(default=28, ge=1, le=480),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    require_website_access(db, principal, website_id, admin=True)
    try:
        return await sync_google_analytics(db, website_id, days)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/websites/{website_id}/integrations/matomo/sync")
async def synchronize_matomo(
    website_id: UUID,
    days: int = Query(default=28, ge=1, le=480),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    require_website_access(db, principal, website_id, admin=True)
    try:
        return await sync_matomo(db, website_id, days)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/websites/{website_id}/integrations/bing_webmaster/sync")
async def synchronize_bing_webmaster(
    website_id: UUID,
    days: int = Query(default=480, ge=1, le=480),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    require_website_access(db, principal, website_id, admin=True)
    try:
        return await sync_bing_webmaster(db, website_id, days)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/websites/{website_id}/integrations/bing_webmaster/backlinks/import")
def import_bing_backlinks(
    website_id: UUID,
    payload: BingBacklinkCsvImport,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, int | str]:
    require_website_access(db, principal, website_id, admin=True)
    try:
        return import_bing_backlink_exports(
            db,
            website_id=website_id,
            domains_csv=payload.domains_csv,
            pages_csv=payload.pages_csv,
            anchors_csv=payload.anchors_csv,
        )
    except InvalidBingBacklinkExport as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

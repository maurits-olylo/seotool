from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import (
    clients,
    content_analysis,
    context_assistant,
    crawls,
    discovery,
    effects,
    exports,
    insights,
    integrations,
    issues,
    jobs,
    opportunities,
    public_estimates,
    recommendations,
    reports,
    system,
    ui,
    users,
    websites,
)
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.security import is_valid_technical_api_key, require_api_key, session_requires_mfa
from app.db.session import engine
from app.services.users import ensure_initial_superuser

configure_logging()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("application_started", environment=get_settings().app_env)
    ensure_initial_superuser()
    yield
    engine.dispose()


app = FastAPI(title=get_settings().app_name, version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def redirect_proxied_http_to_https(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    valid_technical_key = is_valid_technical_api_key(request.headers.get("x-api-key"))
    if (
        request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and request.cookies.get("seo_session")
        and not valid_technical_key
    ):
        origin = request.headers.get("origin")
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        expected_origin = f"{scheme}://{request.headers.get('host', request.url.netloc)}"
        if origin and origin != expected_origin:
            return JSONResponse(status_code=403, content={"detail": "Ongeldige request-origin"})
        if get_settings().app_env == "production" and not origin:
            return JSONResponse(status_code=403, content={"detail": "Request-origin ontbreekt"})
    if (
        get_settings().mfa_enforcement_enabled
        and request.url.path.startswith("/api/v1/")
        and not request.url.path.startswith("/api/v1/me")
        and not valid_technical_key
        and session_requires_mfa(request.cookies.get("seo_session"))
    ):
        return JSONResponse(
            status_code=428,
            content={"detail": "Activeer eerst tweestapsverificatie voor dit beheerdersaccount"},
        )
    if (
        get_settings().app_env == "production"
        and request.headers.get("x-forwarded-proto") == "http"
    ):
        return RedirectResponse(request.url.replace(scheme="https"), status_code=308)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'"
    )
    return response


app.include_router(clients.router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(
    content_analysis.router, prefix="/api/v1", dependencies=[Depends(require_api_key)]
)
app.include_router(
    context_assistant.router, prefix="/api/v1", dependencies=[Depends(require_api_key)]
)
app.include_router(websites.router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(discovery.router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(crawls.router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(issues.router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(jobs.router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(effects.router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(opportunities.router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(
    recommendations.router,
    prefix="/api/v1",
    dependencies=[Depends(require_api_key)],
)
app.include_router(reports.router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(exports.router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(integrations.router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(insights.router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(system.router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(users.router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(users.public_router, prefix="/api/v1")
app.include_router(public_estimates.router, prefix="/api/v1")
app.include_router(integrations.oauth_router, prefix="/api/v1")
app.include_router(ui.router)
app.mount("/ui/assets", StaticFiles(directory=ui.UI_ROOT), name="ui-assets")


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return {"status": "degraded", "database": "unavailable"}
    return {"status": "ok", "database": "ok"}

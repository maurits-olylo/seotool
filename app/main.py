from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import clients, crawls, discovery, exports, integrations, issues, ui, websites
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.security import require_api_key
from app.db.session import engine

configure_logging()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("application_started", environment=get_settings().app_env)
    yield
    engine.dispose()


app = FastAPI(title=get_settings().app_name, version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def redirect_proxied_http_to_https(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    if (
        get_settings().app_env == "production"
        and request.headers.get("x-forwarded-proto") == "http"
    ):
        return RedirectResponse(request.url.replace(scheme="https"), status_code=308)
    return await call_next(request)


app.include_router(clients.router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(websites.router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(discovery.router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(crawls.router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(issues.router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(exports.router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(integrations.router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
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

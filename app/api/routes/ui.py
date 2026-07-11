import hmac
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.security import create_session_token

router = APIRouter(tags=["interface"])
UI_ROOT = Path(__file__).resolve().parents[2] / "ui"


class LoginRequest(BaseModel):
    api_key: str


@router.get("/", include_in_schema=False)
def interface() -> FileResponse:
    return FileResponse(UI_ROOT / "index.html")


@router.post("/ui/login", include_in_schema=False, status_code=status.HTTP_204_NO_CONTENT)
def login(payload: LoginRequest, response: Response) -> Response:
    settings = get_settings()
    if not hmac.compare_digest(payload.api_key, settings.api_key):
        raise HTTPException(status_code=401, detail="Ongeldige API-key")
    response.set_cookie(
        "seo_session",
        create_session_token(),
        max_age=60 * 60 * 12,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="strict",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/ui/logout", include_in_schema=False, status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> Response:
    response.delete_cookie("seo_session", samesite="strict")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response

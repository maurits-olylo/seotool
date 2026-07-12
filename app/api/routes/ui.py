from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    create_session_token,
    hash_password,
    session_user_id,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User

router = APIRouter(tags=["interface"])
UI_ROOT = Path(__file__).resolve().parents[2] / "ui"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


DUMMY_PASSWORD_HASH = hash_password("invalid-login-password")


@router.get("/", include_in_schema=False)
def interface() -> FileResponse:
    return FileResponse(UI_ROOT / "landing.html")


@router.get("/login", include_in_schema=False)
def login_page(
    seo_session: str | None = Cookie(default=None), db: Session = Depends(get_db)
) -> Response:
    user_id = session_user_id(seo_session)
    user = db.get(User, user_id) if user_id else None
    if user and user.is_active:
        return RedirectResponse("/app", status_code=302)
    response = FileResponse(UI_ROOT / "login.html")
    if seo_session:
        response.delete_cookie("seo_session", samesite="lax")
    return response


@router.get("/app", include_in_schema=False)
def app_interface(
    seo_session: str | None = Cookie(default=None), db: Session = Depends(get_db)
) -> Response:
    user_id = session_user_id(seo_session)
    user = db.get(User, user_id) if user_id else None
    if not user or not user.is_active:
        response = RedirectResponse("/login", status_code=302)
        response.delete_cookie("seo_session", samesite="lax")
        return response
    return FileResponse(UI_ROOT / "index.html")


@router.get("/privacy", include_in_schema=False)
def privacy() -> FileResponse:
    return FileResponse(UI_ROOT / "privacy.html")


@router.get("/voorwaarden", include_in_schema=False)
def terms() -> FileResponse:
    return FileResponse(UI_ROOT / "terms.html")


@router.get("/uitnodiging", include_in_schema=False)
def invitation_page() -> FileResponse:
    return FileResponse(UI_ROOT / "invitation.html")


@router.post("/ui/login", include_in_schema=False, status_code=status.HTTP_204_NO_CONTENT)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> Response:
    settings = get_settings()
    email = payload.email.strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    password_hash = user.password_hash if user else DUMMY_PASSWORD_HASH
    if not verify_password(payload.password, password_hash) or not user or not user.is_active:
        raise HTTPException(status_code=401, detail="E-mailadres of wachtwoord is onjuist")
    user.last_login_at = datetime.now(UTC)
    db.commit()
    response.set_cookie(
        "seo_session",
        create_session_token(user.id),
        max_age=60 * 60 * 12,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/ui/logout", include_in_schema=False, status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> Response:
    response.delete_cookie("seo_session", samesite="lax")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response

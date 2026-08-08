import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    create_session_token,
    hash_password,
    require_api_key,
    revoke_session_token,
    session_ttl_seconds,
    session_user_id,
    verify_password,
)
from app.db.session import get_db
from app.models.user import LoginAttempt, User
from app.services.mfa import consume_recovery_code, valid_totp_counter
from app.services.oauth import decrypt_token
from app.services.security_audit import record_security_event
from app.services.staging_render_acceptance import (
    set_staging_render_acceptance_resolved,
    staging_accessibility_acceptance_html,
    staging_render_acceptance_html,
)

router = APIRouter(tags=["interface"])
UI_ROOT = Path(__file__).resolve().parents[2] / "ui"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    mfa_code: str | None = None


class StagingRenderAcceptanceState(BaseModel):
    resolved: bool


DUMMY_PASSWORD_HASH = hash_password("invalid-login-password")
LOGIN_WINDOW = timedelta(minutes=15)
LOGIN_ATTEMPT_LIMIT = 5


def _login_fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


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


@router.get("/staging/render-acceptance", include_in_schema=False)
def staging_render_acceptance_page() -> HTMLResponse:
    if get_settings().app_env != "staging":
        raise HTTPException(status_code=404)
    return HTMLResponse(
        staging_render_acceptance_html(),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/staging/render-acceptance", include_in_schema=False)
def update_staging_render_acceptance_page(
    payload: StagingRenderAcceptanceState,
    _: None = Depends(require_api_key),
) -> dict[str, object]:
    if get_settings().app_env != "staging":
        raise HTTPException(status_code=404)
    set_staging_render_acceptance_resolved(payload.resolved)
    return {"status": "ok", "resolved": payload.resolved}


@router.get("/staging/accessibility-acceptance/{component}", include_in_schema=False)
def staging_accessibility_acceptance_page(component: str) -> HTMLResponse:
    if get_settings().app_env != "staging" or component not in {"component-a", "component-b"}:
        raise HTTPException(status_code=404)
    return HTMLResponse(
        staging_accessibility_acceptance_html(resolved=True),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/ui/login", include_in_schema=False, status_code=status.HTTP_204_NO_CONTENT)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> Response:
    settings = get_settings()
    email = payload.email.strip().lower()
    identifier_hash = _login_fingerprint(email)
    source_hash = _login_fingerprint(request.client.host if request.client else "unknown")
    cutoff = datetime.now(UTC) - LOGIN_WINDOW
    recent_failures = db.scalar(
        select(func.count(LoginAttempt.id)).where(
            LoginAttempt.created_at >= cutoff,
            LoginAttempt.succeeded.is_(False),
            (LoginAttempt.identifier_hash == identifier_hash)
            | (LoginAttempt.source_hash == source_hash),
        )
    )
    if int(recent_failures or 0) >= LOGIN_ATTEMPT_LIMIT:
        raise HTTPException(status_code=429, detail="Probeer het later opnieuw")
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    password_hash = user.password_hash if user else DUMMY_PASSWORD_HASH
    if not verify_password(payload.password, password_hash) or not user or not user.is_active:
        db.add(
            LoginAttempt(
                identifier_hash=identifier_hash,
                source_hash=source_hash,
                succeeded=False,
            )
        )
        record_security_event(
            db,
            event_type="authentication.login",
            result="failed",
            summary="Mislukte inlogpoging",
            target_type="user",
            target_id=user.id if user else None,
            source_hash=source_hash,
        )
        db.commit()
        raise HTTPException(status_code=401, detail="E-mailadres of wachtwoord is onjuist")
    if user.mfa_enabled:
        if not payload.mfa_code:
            return JSONResponse(status_code=202, content={"mfa_required": True})
        counter = valid_totp_counter(
            decrypt_token(user.mfa_secret_encrypted) or "",
            payload.mfa_code,
            last_counter=user.mfa_last_counter,
        )
        if counter is not None:
            user.mfa_last_counter = counter
        else:
            remaining = consume_recovery_code(
                payload.mfa_code, user.mfa_recovery_code_hashes or []
            )
            if remaining is None:
                db.add(
                    LoginAttempt(
                        identifier_hash=identifier_hash,
                        source_hash=source_hash,
                        succeeded=False,
                    )
                )
                record_security_event(
                    db,
                    event_type="authentication.mfa",
                    result="failed",
                    summary="Mislukte MFA-verificatie",
                    actor_user_id=user.id,
                    target_type="user",
                    target_id=user.id,
                    source_hash=source_hash,
                )
                db.commit()
                raise HTTPException(status_code=401, detail="De verificatiecode is onjuist")
            user.mfa_recovery_code_hashes = remaining
    db.execute(
        delete(LoginAttempt).where(
            (LoginAttempt.identifier_hash == identifier_hash)
            | (LoginAttempt.source_hash == source_hash)
        )
    )
    user.last_login_at = datetime.now(UTC)
    record_security_event(
        db,
        event_type="authentication.login",
        result="succeeded",
        summary="Gebruiker ingelogd",
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        source_hash=source_hash,
        details={"mfa_used": user.mfa_enabled},
    )
    db.commit()
    response.set_cookie(
        "seo_session",
        create_session_token(user.id),
        max_age=session_ttl_seconds(user.role),
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/ui/logout", include_in_schema=False, status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, seo_session: str | None = Cookie(default=None)) -> Response:
    revoke_session_token(seo_session)
    response.delete_cookie("seo_session", samesite="lax")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response

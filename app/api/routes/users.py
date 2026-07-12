from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.models.user import ClientMembership, User
from app.schemas.users import CurrentUserRead

router = APIRouter(tags=["users"])


@router.get("/me", response_model=CurrentUserRead)
def current_user(
    principal: Principal = Depends(require_api_key), db: Session = Depends(get_db)
) -> dict[str, object]:
    user = db.get(User, principal.user_id) if principal.user_id else None
    memberships = (
        list(
            db.scalars(
                select(ClientMembership).where(ClientMembership.user_id == principal.user_id)
            )
        )
        if principal.user_id
        else []
    )
    return {
        "id": principal.user_id,
        "email": user.email if user else None,
        "display_name": user.display_name if user else None,
        "role": principal.role,
        "memberships": [
            {"client_id": membership.client_id, "role": membership.role}
            for membership in memberships
        ],
    }

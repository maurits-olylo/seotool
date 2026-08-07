from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.schemas.context_assistant import ContextAssistantAnswer, ContextAssistantQuestion
from app.services.authorization import require_website_access
from app.services.context_assistant import ContextAssistantError, answer_context_question

router = APIRouter(prefix="/websites/{website_id}/context-assistant", tags=["context-assistant"])


@router.post("/answer", response_model=ContextAssistantAnswer)
def answer(
    website_id: UUID,
    payload: ContextAssistantQuestion,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    require_website_access(db, principal, website_id)
    try:
        return answer_context_question(
            db,
            website_id=website_id,
            context_type=payload.context_type,
            context_id=payload.context_id,
            question=payload.question,
        )
    except ContextAssistantError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

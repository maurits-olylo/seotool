from datetime import date, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import Principal, require_api_key
from app.db.session import get_db
from app.services.authorization import require_global_role, require_website_access
from app.services.consultant_insights import build_consultant_insights

router = APIRouter(tags=["insights"])
InsightPeriod = Literal["28", "90"]


@router.get("/websites/{website_id}/consultant-insights")
def consultant_insights(
    website_id: UUID,
    days: InsightPeriod = Query(default="28"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
) -> dict[str, object]:
    require_global_role(principal, "superuser", "admin", "user")
    require_website_access(db, principal, website_id)
    period_days = int(days)
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=period_days - 1)
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=period_days - 1)
    insights = build_consultant_insights(
        db,
        website_id,
        start,
        end,
        previous_start,
        previous_end,
    )
    return {
        "website_id": str(website_id),
        "days": period_days,
        "start_date": start,
        "end_date": end,
        "previous_start_date": previous_start,
        "previous_end_date": previous_end,
        "search": insights["search"],
        "content": insights["content"],
        "conversion": insights["conversion"],
        "conversion_context": insights["conversion_context"],
    }

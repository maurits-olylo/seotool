from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, status

from app.schemas.public_estimate import PublicWebsiteEstimateRead, PublicWebsiteEstimateRequest
from app.services.public_estimate import PublicEstimateError, estimate_public_website

router = APIRouter(tags=["public-estimates"])
_requests: dict[str, deque[datetime]] = defaultdict(deque)


@router.post(
    "/public/website-estimate",
    response_model=PublicWebsiteEstimateRead,
    status_code=status.HTTP_200_OK,
)
def public_website_estimate(
    payload: PublicWebsiteEstimateRequest, request: Request
) -> PublicWebsiteEstimateRead:
    _enforce_rate_limit(request.client.host if request.client else "unknown")
    try:
        result = estimate_public_website(str(payload.url))
    except PublicEstimateError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PublicWebsiteEstimateRead(**result.__dict__)


def _enforce_rate_limit(client_key: str, *, limit: int = 5) -> None:
    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=1)
    entries = _requests[client_key]
    while entries and entries[0] <= cutoff:
        entries.popleft()
    if len(entries) >= limit:
        raise HTTPException(status_code=429, detail="Probeer het over een minuut opnieuw")
    entries.append(now)

from datetime import datetime
from uuid import UUID

from app.schemas.common import Timestamped


class AssetRead(Timestamped):
    website_id: UUID
    url_id: UUID
    url: str
    kind: str
    content_type: str | None
    status_code: int | None
    final_url: str | None
    response_size: int | None
    etag: str | None
    last_modified: str | None
    first_seen_at: datetime
    last_checked_at: datetime

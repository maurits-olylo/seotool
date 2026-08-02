from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.assets import Asset
from app.models.crawl import UrlSnapshot
from app.models.discovery import Url
from app.services.url_filtering import asset_kind


def update_asset_record(db: Session, *, url: Url, snapshot: UrlSnapshot) -> Asset | None:
    kind = asset_kind(url.normalized_url, snapshot.content_type)
    if kind is None:
        return None
    asset = db.scalar(select(Asset).where(Asset.url_id == url.id))
    if asset is None:
        asset = Asset(website_id=url.website_id, url_id=url.id, kind=kind)
        db.add(asset)
    asset.kind = kind
    asset.content_type = snapshot.content_type
    asset.status_code = snapshot.status_code
    asset.final_url = snapshot.final_url
    asset.response_size = snapshot.response_size
    asset.etag = snapshot.etag
    asset.last_modified = snapshot.last_modified
    asset.last_checked_at = snapshot.checked_at
    db.flush()
    return asset

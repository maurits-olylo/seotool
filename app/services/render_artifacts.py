import hashlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings


@dataclass(frozen=True)
class StoredRenderArtifact:
    key: str
    sha256: str
    size: int
    expires_at: datetime


def store_render_screenshot(
    website_id: UUID, observation_id: UUID, content: bytes
) -> StoredRenderArtifact:
    settings = get_settings()
    root = Path(settings.render_artifact_dir)
    prune_expired_render_artifacts(
        root, retention_days=settings.render_artifact_retention_days
    )
    key = f"{website_id}/{observation_id}.png"
    destination = root / key
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_bytes(content)
    os.chmod(temporary, 0o600)
    temporary.replace(destination)
    return StoredRenderArtifact(
        key=key,
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
        expires_at=datetime.now(UTC)
        + timedelta(days=settings.render_artifact_retention_days),
    )


def prune_expired_render_artifacts(
    root: Path, *, retention_days: int, limit: int = 100
) -> int:
    if not root.exists():
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    removed = 0
    for path in sorted(root.glob("*/*.png")):
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        if modified_at >= cutoff:
            continue
        path.unlink()
        removed += 1
        if removed >= limit:
            break
    return removed

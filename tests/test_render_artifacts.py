import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.services import render_artifacts


def test_render_artifact_is_private_hashed_and_prunes_expired_files(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    old = tmp_path / "old" / "expired.png"
    old.parent.mkdir()
    old.write_bytes(b"old")
    old_time = (datetime.now(UTC) - timedelta(days=91)).timestamp()
    os.utime(old, (old_time, old_time))
    monkeypatch.setattr(
        render_artifacts,
        "get_settings",
        lambda: SimpleNamespace(
            render_artifact_dir=str(tmp_path), render_artifact_retention_days=90
        ),
    )

    website_id = uuid4()
    observation_id = uuid4()
    stored = render_artifacts.store_render_screenshot(
        website_id, observation_id, b"png-content"
    )

    artifact = tmp_path / stored.key
    assert artifact.read_bytes() == b"png-content"
    assert artifact.stat().st_mode & 0o777 == 0o600
    assert stored.size == 11
    assert len(stored.sha256) == 64
    assert not old.exists()


def test_render_artifact_path_rejects_traversal(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        render_artifacts,
        "get_settings",
        lambda: SimpleNamespace(render_artifact_dir=str(tmp_path)),
    )

    assert render_artifacts.render_artifact_path("site/observation.png") == (
        tmp_path / "site" / "observation.png"
    )
    for unsafe in ("../secret.png", "site/../../secret.png", "site/file.txt"):
        try:
            render_artifacts.render_artifact_path(unsafe)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Unsafe key accepted: {unsafe}")

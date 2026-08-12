import hashlib
import importlib.util
import stat
from pathlib import Path

import pytest


def _module():  # type: ignore[no-untyped-def]
    path = Path(__file__).resolve().parents[1] / "scripts/offsite-backup.py"
    spec = importlib.util.spec_from_file_location("offsite_backup", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_credentials_require_restricted_file(tmp_path: Path) -> None:
    module = _module()
    credentials = tmp_path / "credentials"
    credentials.write_text("AWS_ACCESS_KEY_ID=test\nAWS_SECRET_ACCESS_KEY=secret\n")
    credentials.chmod(0o644)

    with pytest.raises(module.OffsiteBackupError, match="mode 0400 or 0600"):
        module._credentials(credentials)


def test_upload_resolves_latest_link_and_requires_compliance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    backup = tmp_path / "seo-monitor-production-20260812T120000Z.tar.enc"
    backup.write_bytes(b"encrypted-backup")
    latest = tmp_path / "seo-monitor-production-latest.tar.enc"
    latest.symlink_to(backup.name)
    monkeypatch.setenv("S3_BACKUP_PREFIX", "seo-monitor/production")
    monkeypatch.setenv("S3_BACKUP_OBJECT_LOCK_DAYS", "30")

    class FakeClient:
        def __init__(self) -> None:
            self.requests: list[tuple[str, str, dict[str, str]]] = []

        def request(  # type: ignore[no-untyped-def]
            self, method, key, *, body=b"", body_path=None, query="", extra_headers=None
        ):
            self.requests.append((method, key, extra_headers or {}))
            if method == "HEAD":
                return b"", {
                    "content-length": str(backup.stat().st_size),
                    "x-amz-meta-sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
                }
            if query == "retention=":
                return (
                    b"<Retention><Mode>COMPLIANCE</Mode>"
                    b"<RetainUntilDate>2026-09-11T12:00:00Z</RetainUntilDate></Retention>",
                    {},
                )
            return b"", {}

    client = FakeClient()
    module.upload(client, latest)

    method, key, headers = client.requests[0]
    assert method == "PUT"
    assert key.endswith(backup.name)
    assert not key.endswith(latest.name)
    assert headers["x-amz-object-lock-mode"] == "COMPLIANCE"
    assert headers["x-amz-meta-sha256"] == hashlib.sha256(backup.read_bytes()).hexdigest()


def test_download_is_atomic_and_checksum_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    body = b"encrypted-backup"
    checksum = hashlib.sha256(body).hexdigest()

    class FakeClient:
        def request(self, method, key):  # type: ignore[no-untyped-def]
            assert method == "GET"
            assert key == "seo-monitor/production/archive.tar.enc"
            return body, {"x-amz-meta-sha256": checksum}

    destination = tmp_path / "restore" / "archive.tar.enc"
    module.download(FakeClient(), "seo-monitor/production/archive.tar.enc", destination)

    assert destination.read_bytes() == body
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert destination.with_suffix(".enc.sha256").read_text() == (
        f"{checksum}  {destination.name}\n"
    )
    assert not any(path.name.endswith(".incomplete") for path in destination.parent.iterdir())

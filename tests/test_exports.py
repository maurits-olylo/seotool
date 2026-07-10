from pathlib import Path

import pytest

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.discovery import Url
from app.models.exports import Export
from app.models.website import Website, WebsiteSettings
from app.services import exports as export_service


@pytest.mark.parametrize("export_type,suffix", [("urls", "csv"), ("excel", "xlsx")])
def test_generates_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    export_type: str,
    suffix: str,
) -> None:
    monkeypatch.setattr(export_service, "EXPORT_ROOT", tmp_path)
    with SessionLocal() as db:
        client = Client(name="Export client")
        website = Website(client=client, name="Export site", base_url="https://example.com")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        db.add(Url(website_id=website.id, normalized_url="https://example.com/"))
        export = Export(website_id=website.id, export_type=export_type)
        db.add(export)
        db.commit()
        export_id = export.id

    export_service.generate_export(str(export_id))

    with SessionLocal() as db:
        completed = db.get(Export, export_id)
        assert completed and completed.status == "succeeded"
        path = Path(completed.file_path or "")
        assert path.suffix == f".{suffix}"
        assert path.stat().st_size > 0

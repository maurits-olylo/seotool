from datetime import timedelta
from pathlib import Path

import pytest

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.common import utc_now
from app.models.crawl import CrawlRun, UrlLink, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.exports import Export
from app.models.issues import Change, Issue
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


def test_datasets_include_human_readable_urls() -> None:
    with SessionLocal() as db:
        client = Client(name="Readable export client")
        website = Website(client=client, name="Readable site", base_url="https://example.com")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        source = Url(website_id=website.id, normalized_url="https://example.com/source")
        target = Url(website_id=website.id, normalized_url="https://example.com/target")
        db.add_all([source, target])
        db.flush()
        job = CrawlJob(website_id=website.id, job_type="full_site_crawl")
        db.add(job)
        db.flush()
        run = CrawlRun(
            crawl_job_id=job.id,
            website_id=website.id,
            crawl_type="full_site_crawl",
            status="succeeded",
            finished_at=utc_now(),
        )
        db.add(run)
        db.flush()
        old_job = CrawlJob(website_id=website.id, job_type="full_site_crawl")
        db.add(old_job)
        db.flush()
        old_run = CrawlRun(
            crawl_job_id=old_job.id,
            website_id=website.id,
            crawl_type="full_site_crawl",
            status="succeeded",
            finished_at=utc_now() - timedelta(days=1),
        )
        db.add(old_run)
        db.flush()
        snapshot = UrlSnapshot(
            url_id=target.id,
            crawl_run_id=run.id,
            requested_url=target.normalized_url,
        )
        db.add(snapshot)
        db.flush()
        db.add_all(
            [
                Issue(
                    website_id=website.id,
                    url_id=target.id,
                    issue_type="missing_title",
                    category="onpage",
                    severity="medium",
                    title="Title ontbreekt",
                    description="Test",
                    recommended_action="Herstel",
                ),
                Change(
                    website_id=website.id,
                    url_id=target.id,
                    current_snapshot_id=snapshot.id,
                    change_type="new_url",
                ),
                UrlLink(
                    crawl_run_id=run.id,
                    source_url_id=source.id,
                    target_url=target.normalized_url,
                    target_url_id=target.id,
                    is_internal=True,
                    is_nofollow=False,
                ),
                UrlLink(
                    crawl_run_id=old_run.id,
                    source_url_id=source.id,
                    target_url=target.normalized_url,
                    target_url_id=target.id,
                    is_internal=True,
                    is_nofollow=False,
                ),
            ]
        )
        db.commit()

        datasets = export_service._datasets(db, website.id)

        assert datasets["urls"][0][:2] == ["url_id", "url"]
        assert datasets["issues"][0][:2] == ["url_id", "url"]
        assert datasets["issues"][1][0][1] == target.normalized_url
        assert datasets["changes"][0][:2] == ["url_id", "url"]
        assert datasets["changes"][1][0][1] == target.normalized_url
        assert datasets["links"][0][:4] == [
            "source_url_id",
            "source_url",
            "target_url_id",
            "target_url",
        ]
        assert datasets["links"][1][0][1] == source.normalized_url
        assert len(datasets["links"][1]) == 1

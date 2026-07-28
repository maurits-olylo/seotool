from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.issues import Change
from app.models.website import Website, WebsiteSettings
from app.services.change_history import change_history_counts, reset_change_history


def _change_fixture(db, *, job_status: str = "succeeded"):  # type: ignore[no-untyped-def]
    client = Client(name="Change cleanup client")
    website = Website(
        client=client,
        name="Change cleanup site",
        base_url="https://example.com",
        settings=WebsiteSettings(),
    )
    db.add(website)
    db.flush()
    url = Url(website_id=website.id, normalized_url="https://example.com/page")
    job = CrawlJob(website_id=website.id, job_type="full_site_crawl", status=job_status)
    db.add_all([url, job])
    db.flush()
    run = CrawlRun(
        crawl_job_id=job.id,
        website_id=website.id,
        crawl_type=job.job_type,
        status=job_status,
    )
    db.add(run)
    db.flush()
    snapshot = UrlSnapshot(
        url_id=url.id,
        crawl_run_id=run.id,
        requested_url=url.normalized_url,
    )
    db.add(snapshot)
    db.flush()
    db.add(
        Change(
            website_id=website.id,
            url_id=url.id,
            current_snapshot_id=snapshot.id,
            change_type="main_content_changed",
        )
    )
    db.commit()
    return website.id


def test_change_history_audit_and_reset_preserve_snapshots() -> None:
    with SessionLocal() as db:
        website_id = _change_fixture(db)

        audit = change_history_counts(db)
        result = reset_change_history(db, website_id=website_id)
        remaining_changes = db.query(Change).count()
        remaining_snapshots = db.query(UrlSnapshot).count()

    assert audit["total_changes"] == 1
    assert result.deleted == 1
    assert remaining_changes == 0
    assert remaining_snapshots == 1


def test_change_history_reset_refuses_active_crawl() -> None:
    with SessionLocal() as db:
        website_id = _change_fixture(db, job_status="running")

        try:
            reset_change_history(db, website_id=website_id)
        except RuntimeError as exc:
            assert "crawl actief" in str(exc)
        else:
            raise AssertionError("Reset had een actieve crawl moeten weigeren")

        assert db.query(Change).count() == 1

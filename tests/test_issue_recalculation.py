from sqlalchemy import select

from app.db.session import SessionLocal
from app.jobs import execute_crawl_job
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.issues import Change, Issue
from app.models.website import Website, WebsiteSettings


def test_recalculates_issues_from_latest_full_crawl_without_fetching(monkeypatch) -> None:
    with SessionLocal() as db:
        website = Website(
            client=Client(name="Recalculation client"),
            name="Recalculation site",
            base_url="https://example.com/",
        )
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        source_job = CrawlJob(
            website_id=website.id,
            job_type="full_site_crawl",
            status="succeeded",
        )
        db.add(source_job)
        db.flush()
        source_run = CrawlRun(
            crawl_job_id=source_job.id,
            website_id=website.id,
            crawl_type="full_site_crawl",
            status="succeeded",
            discovered_urls=1,
            crawled_urls=1,
            html_urls=1,
        )
        db.add(source_run)
        db.flush()
        url = Url(
            website_id=website.id,
            normalized_url="https://example.com/artikelen/privacy",
            is_active=True,
        )
        db.add(url)
        db.flush()
        snapshot = UrlSnapshot(
            url_id=url.id,
            crawl_run_id=source_run.id,
            requested_url=url.normalized_url,
            final_url=url.normalized_url,
            status_code=200,
            redirect_chain=[],
            word_count=25,
            is_indexable=True,
        )
        db.add(snapshot)
        db.flush()
        stale_issue = Issue(
            website_id=website.id,
            url_id=url.id,
            issue_type="thin_content",
            category="onpage",
            severity="medium",
            title="Nagenoeg lege pagina",
            description="Verouderd signaal.",
            recommended_action="Controleer de pagina.",
        )
        stale_cluster = Issue(
            website_id=website.id,
            url_id=None,
            issue_type="template_signal_clusters",
            category="onpage",
            severity="medium",
            title="Historische clusters",
            description="Verouderde clusterindeling.",
            recommended_action="Controleer de clusters.",
        )
        recalculation = CrawlJob(
            website_id=website.id,
            job_type="recalculate_issues",
        )
        existing_change = Change(
            website_id=website.id,
            url_id=url.id,
            current_snapshot_id=snapshot.id,
            change_type="new_url",
            field_name="url",
            new_value=url.normalized_url,
        )
        db.add_all([stale_issue, stale_cluster, recalculation, existing_change])
        db.commit()
        recalculation_id = recalculation.id
        stale_issue_id = stale_issue.id
        stale_cluster_id = stale_cluster.id

    monkeypatch.setattr(
        "app.jobs.fetch_url",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network fetch")),
    )

    execute_crawl_job(str(recalculation_id))

    with SessionLocal() as db:
        job = db.get(CrawlJob, recalculation_id)
        run = db.scalar(select(CrawlRun).where(CrawlRun.crawl_job_id == recalculation_id))
        assert job is not None and job.status == "succeeded"
        assert run is not None
        assert run.status == "succeeded"
        assert run.crawl_type == "recalculate_issues"
        assert run.crawled_urls == 1
        assert db.scalar(select(Change).where(Change.website_id == job.website_id)) is not None
        assert (
            len(list(db.scalars(select(Change).where(Change.website_id == job.website_id)))) == 1
        )
        assert db.get(Issue, stale_issue_id).status == "verified"  # type: ignore[union-attr]
        assert db.get(Issue, stale_cluster_id).status == "resolved"  # type: ignore[union-attr]

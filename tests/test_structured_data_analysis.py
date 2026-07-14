from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.issues import Issue
from app.models.website import Website, WebsiteSettings
from app.services.structured_data_analysis import analyze_breadcrumb_consistency


def test_reports_breadcrumb_gap_only_when_site_consistently_uses_schema() -> None:
    with SessionLocal() as db:
        client = Client(name="Breadcrumb client")
        website = Website(client=client, name="Breadcrumb site", base_url="https://example.com/")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        run = _run(db, website.id)
        urls = [_url(db, website.id, number) for number in range(6)]
        for index, url in enumerate(urls):
            db.add(_snapshot(url, run, has_breadcrumb=index < 3))
        db.flush()

        found = analyze_breadcrumb_consistency(db, website_id=website.id, crawl_run_id=run.id)

        assert len(found) == 3
        assert {issue.issue_type for issue in found} == {"missing_breadcrumb_schema"}
        assert {issue.url_id for issue in found} == {url.id for url in urls[3:]}

        second_run = _run(db, website.id)
        for url in urls:
            db.add(_snapshot(url, second_run, has_breadcrumb=True))
        db.flush()

        assert (
            analyze_breadcrumb_consistency(db, website_id=website.id, crawl_run_id=second_run.id)
            == []
        )
        assert set(db.scalars(select(Issue.status))) == {"resolved"}


def _url(db, website_id, number):  # type: ignore[no-untyped-def]
    url = Url(
        website_id=website_id,
        normalized_url=f"https://example.com/category/page-{number}",
        current_status_code=200,
        is_active=True,
        is_indexable=True,
        crawl_depth=2,
    )
    db.add(url)
    db.flush()
    return url


def _run(db, website_id):  # type: ignore[no-untyped-def]
    job = CrawlJob(website_id=website_id, job_type="full_site_crawl")
    db.add(job)
    db.flush()
    run = CrawlRun(
        crawl_job_id=job.id,
        website_id=website_id,
        crawl_type="full_site_crawl",
    )
    db.add(run)
    db.flush()
    return run


def _snapshot(url, run, *, has_breadcrumb):  # type: ignore[no-untyped-def]
    return UrlSnapshot(
        url_id=url.id,
        crawl_run_id=run.id,
        requested_url=url.normalized_url,
        final_url=url.normalized_url,
        status_code=200,
        content_type="text/html",
        redirect_chain=[],
        schema_types=["BreadcrumbList"] if has_breadcrumb else [],
        schema_data=[],
        is_indexable=True,
    )

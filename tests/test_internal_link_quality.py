from datetime import date

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlLink, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.integrations import SearchConsoleMetric
from app.models.issues import Issue, IssueOccurrence
from app.models.website import Website, WebsiteSettings
from app.services.internal_link_analysis import analyze_internal_link_quality


def test_detects_redirect_deep_page_and_weakly_linked_important_page() -> None:
    with SessionLocal() as db:
        client = Client(name="Link client")
        website = Website(client=client, name="Link site", base_url="https://example.com/")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        source = _url(db, website.id, "/source", depth=1)
        redirect = _url(
            db,
            website.id,
            "/old",
            depth=2,
            final_url="https://example.com/new",
        )
        deep = _url(db, website.id, "/deep", depth=5)
        important = _url(db, website.id, "/important", depth=2)
        run = _run(db, website.id)
        for url in (source, redirect, deep, important):
            db.add(_snapshot(url, run))
        db.add_all(
            [
                UrlLink(
                    crawl_run_id=run.id,
                    source_url_id=source.id,
                    target_url=redirect.normalized_url,
                    target_url_id=redirect.id,
                    anchor_text="Oud",
                    is_internal=True,
                    is_nofollow=False,
                ),
                UrlLink(
                    crawl_run_id=run.id,
                    source_url_id=source.id,
                    target_url=important.normalized_url,
                    target_url_id=important.id,
                    anchor_text="Belangrijk",
                    is_internal=True,
                    is_nofollow=False,
                ),
                SearchConsoleMetric(
                    website_id=website.id,
                    url_id=important.id,
                    date=date.today(),
                    page_url=important.normalized_url,
                    clicks=12,
                    impressions=100,
                ),
            ]
        )
        db.flush()

        found = analyze_internal_link_quality(
            db, website_id=website.id, crawl_run_id=run.id
        )

        assert {issue.issue_type for issue in found} == {
            "deep_page",
            "important_page_few_internal_links",
            "internally_linked_redirect",
        }
        redirect_issue = db.scalar(
            select(Issue).where(Issue.issue_type == "internally_linked_redirect")
        )
        assert redirect_issue is not None
        occurrence = db.scalar(
            select(IssueOccurrence).where(IssueOccurrence.issue_id == redirect_issue.id)
        )
        assert occurrence is not None
        assert occurrence.evidence["final_url"] == "https://example.com/new"
        assert occurrence.evidence["source_urls"] == ["https://example.com/source"]

        second_run = _run(db, website.id)
        redirect.current_final_url = redirect.normalized_url
        deep.crawl_depth = 2
        db.add_all(_snapshot(url, second_run) for url in (source, redirect, deep, important))
        db.add_all(
            [
                UrlLink(
                    crawl_run_id=second_run.id,
                    source_url_id=source.id,
                    target_url=important.normalized_url,
                    target_url_id=important.id,
                    anchor_text="Belangrijk",
                    is_internal=True,
                    is_nofollow=False,
                ),
                UrlLink(
                    crawl_run_id=second_run.id,
                    source_url_id=deep.id,
                    target_url=important.normalized_url,
                    target_url_id=important.id,
                    anchor_text="Ook belangrijk",
                    is_internal=True,
                    is_nofollow=False,
                ),
            ]
        )
        db.flush()

        assert (
            analyze_internal_link_quality(
                db, website_id=website.id, crawl_run_id=second_run.id
            )
            == []
        )
        assert set(db.scalars(select(Issue.status))) == {"resolved"}


def _url(db, website_id, path, *, depth, final_url=None):  # type: ignore[no-untyped-def]
    normalized_url = f"https://example.com{path}"
    url = Url(
        website_id=website_id,
        normalized_url=normalized_url,
        current_status_code=200,
        current_final_url=final_url or normalized_url,
        is_active=True,
        is_indexable=True,
        crawl_depth=depth,
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


def _snapshot(url, run):  # type: ignore[no-untyped-def]
    return UrlSnapshot(
        url_id=url.id,
        crawl_run_id=run.id,
        requested_url=url.normalized_url,
        final_url=url.current_final_url,
        status_code=200,
        content_type="text/html",
        redirect_chain=[],
        is_indexable=True,
    )

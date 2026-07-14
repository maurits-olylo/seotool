from datetime import date

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url, UrlSource
from app.models.integrations import SearchConsoleMetric
from app.models.issues import Issue, IssueOccurrence
from app.models.website import Website, WebsiteSettings
from app.services.indexation_analysis import analyze_indexation_consistency
from app.services.issue_engine import reconcile_issues
from app.services.technical_checks import IssueSignal


def test_adds_sitemap_and_performance_context_to_indexation_issues() -> None:
    with SessionLocal() as db:
        client = Client(name="Indexation client")
        website = Website(client=client, name="Indexation site", base_url="https://example.com/")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        run = _run(db, website.id)
        noindex = _url(db, website.id, "/noindex")
        canonicalized = _url(db, website.id, "/filter?c=one")
        redirect = _url(db, website.id, "/old")
        for url in (noindex, canonicalized, redirect):
            db.add(
                UrlSource(
                    url_id=url.id,
                    source_type="sitemap",
                    source_url="https://example.com/sitemap.xml",
                )
            )
        noindex_snapshot = _snapshot(noindex, run, is_indexable=False)
        canonical_snapshot = _snapshot(
            canonicalized,
            run,
            canonical="https://example.com/filter",
        )
        redirect_snapshot = _snapshot(
            redirect,
            run,
            final_url="https://example.com/new",
            redirect_chain=[
                {
                    "url": redirect.normalized_url,
                    "status_code": 301,
                    "target": "https://example.com/new",
                }
            ],
        )
        db.add_all([noindex_snapshot, canonical_snapshot, redirect_snapshot])
        db.add(
            SearchConsoleMetric(
                website_id=website.id,
                url_id=noindex.id,
                date=date.today(),
                page_url=noindex.normalized_url,
                clicks=12,
                impressions=200,
            )
        )
        db.flush()
        reconcile_issues(
            db,
            website_id=website.id,
            url_id=noindex.id,
            crawl_run_id=run.id,
            snapshot_id=noindex_snapshot.id,
            signals=[
                IssueSignal(
                    "unexpected_noindex",
                    "indexation",
                    "medium",
                    "Pagina heeft een noindex-instructie",
                    "Generieke melding.",
                    "Controleer de pagina.",
                    {"generic": True},
                )
            ],
            checked_issue_types={"unexpected_noindex"},
        )

        found = analyze_indexation_consistency(db, website_id=website.id, crawl_run_id=run.id)

        assert {issue.issue_type for issue in found} == {
            "canonical_other_url",
            "sitemap_redirect",
            "unexpected_noindex",
        }
        noindex_issue = db.scalar(select(Issue).where(Issue.issue_type == "unexpected_noindex"))
        assert noindex_issue is not None
        assert noindex_issue.severity == "high"
        assert noindex_issue.title == "Belangrijke pagina is niet indexeerbaar"
        occurrence = db.scalar(
            select(IssueOccurrence).where(IssueOccurrence.issue_id == noindex_issue.id)
        )
        assert occurrence is not None
        assert occurrence.evidence["in_current_sitemap"] is True


def _url(db, website_id, path):  # type: ignore[no-untyped-def]
    url = Url(
        website_id=website_id,
        normalized_url=f"https://example.com{path}",
        current_status_code=200,
        is_active=True,
        is_indexable=True,
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


def _snapshot(
    url,
    run,
    *,
    is_indexable=True,
    canonical=None,
    final_url=None,
    redirect_chain=None,
):  # type: ignore[no-untyped-def]
    return UrlSnapshot(
        url_id=url.id,
        crawl_run_id=run.id,
        requested_url=url.normalized_url,
        final_url=final_url or url.normalized_url,
        status_code=200,
        content_type="text/html",
        redirect_chain=redirect_chain or [],
        canonical=canonical,
        is_indexable=is_indexable,
    )

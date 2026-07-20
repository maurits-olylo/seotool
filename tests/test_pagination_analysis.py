from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.issues import Issue, IssueOccurrence
from app.models.website import Website, WebsiteSettings
from app.services.pagination_analysis import analyze_pagination_series


def test_groups_pagination_noise_and_boundary_errors_into_one_review() -> None:
    with SessionLocal() as db:
        client = Client(name="Pagination client")
        website = Website(client=client, name="Pagination", base_url="https://example.com")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        job = CrawlJob(website_id=website.id, job_type="full_site_crawl")
        db.add(job)
        db.flush()
        run = CrawlRun(
            crawl_job_id=job.id,
            website_id=website.id,
            crawl_type="full_site_crawl",
        )
        db.add(run)
        db.flush()
        for page in range(4):
            url = Url(
                website_id=website.id,
                normalized_url=f"https://example.com/articles?page={page}",
                current_status_code=404 if page == 0 else 200,
                is_indexable=page != 0,
            )
            db.add(url)
            db.flush()
            db.add(
                UrlSnapshot(
                    url_id=url.id,
                    crawl_run_id=run.id,
                    requested_url=url.normalized_url,
                    final_url=url.normalized_url,
                    status_code=404 if page == 0 else 200,
                    redirect_chain=[],
                    is_indexable=page != 0,
                )
            )
            if page:
                for issue_type in ("deep_page", "duplicate_title"):
                    db.add(
                        Issue(
                            website_id=website.id,
                            url_id=url.id,
                            issue_type=issue_type,
                            category="onpage",
                            severity="low",
                            title=issue_type,
                            description="Herhaald pagineringssignaal.",
                            recommended_action="Controleer de reeks.",
                        )
                    )
        db.flush()

        found = analyze_pagination_series(db, website_id=website.id, crawl_run_id=run.id)
        db.flush()

        assert len(found) == 1
        assert found[0].title == "4 paginerings-URL's vormen 1 herkenbare reeks"
        occurrence = db.scalar(
            select(IssueOccurrence).where(IssueOccurrence.issue_id == found[0].id)
        )
        assert occurrence is not None
        assert occurrence.evidence["series_count"] == 1
        pattern = occurrence.evidence["patterns"][0]
        assert pattern["pattern"] == "https://example.com/articles?page=*"
        assert pattern["valid_page_range"] == [1, 3]
        assert pattern["error_pages"] == ["https://example.com/articles?page=0"]
        assert pattern["signal_counts"]["deep_page"] == 3

        for issue in db.scalars(
            select(Issue).where(Issue.url_id.is_not(None))
        ):
            issue.status = "resolved"
        next_job = CrawlJob(website_id=website.id, job_type="full_site_crawl")
        db.add(next_job)
        db.flush()
        next_run = CrawlRun(
            crawl_job_id=next_job.id,
            website_id=website.id,
            crawl_type="full_site_crawl",
        )
        db.add(next_run)
        db.flush()
        for page in range(4):
            db.add(
                UrlSnapshot(
                    url_id=db.scalar(
                        select(Url.id).where(
                            Url.normalized_url == f"https://example.com/articles?page={page}"
                        )
                    ),
                    crawl_run_id=next_run.id,
                    requested_url=f"https://example.com/articles?page={page}",
                    final_url=f"https://example.com/articles?page={page}",
                    status_code=200,
                    redirect_chain=[],
                    is_indexable=True,
                )
            )
        db.flush()

        assert analyze_pagination_series(
            db, website_id=website.id, crawl_run_id=next_run.id
        ) == []
        assert found[0].status == "resolved"

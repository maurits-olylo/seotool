from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.issues import Issue, IssueOccurrence
from app.models.website import Website, WebsiteSettings
from app.services.thin_content_analysis import analyze_contextual_thin_content


def test_reports_only_clear_outlier_within_url_family() -> None:
    with SessionLocal() as db:
        website, run = _website_and_run(db)
        word_counts = [320, 300, 280, 260, 90]
        urls: list[Url] = []
        for index, word_count in enumerate(word_counts):
            url = Url(
                website_id=website.id,
                normalized_url=f"https://example.com/artikelen/pagina-{index}",
            )
            db.add(url)
            db.flush()
            urls.append(url)
            db.add(_snapshot(url, run, word_count))
        db.flush()

        analyze_contextual_thin_content(
            db,
            website_id=website.id,
            crawl_run_id=run.id,
        )
        db.commit()

        issues = list(db.scalars(select(Issue).where(Issue.issue_type == "thin_content")))
        assert [issue.url_id for issue in issues] == [urls[-1].id]
        occurrence = db.scalar(
            select(IssueOccurrence).where(IssueOccurrence.issue_id == issues[0].id)
        )
        assert occurrence is not None
        assert occurrence.evidence["baseline_scope"] == "url_family"
        assert occurrence.evidence["baseline_word_count"] == 280.0
        assert occurrence.evidence["cohort_size"] == 5


def test_accepts_short_functional_pages_and_site_norm() -> None:
    with SessionLocal() as db:
        website, run = _website_and_run(db)
        paths = [
            ("contact", 12),
            ("nieuwsbrief", 18),
            ("nieuwsbrieven/human-nieuwsbrief", 18),
            ("newsletters/weekly-update", 18),
            ("privacyverklaring", 20),
            ("copyright", 15),
            ("enquete", 10),
            ("offerte-samenstellen", 25),
            ("kort/pagina-1", 90),
            ("kort/pagina-2", 100),
            ("kort/pagina-3", 110),
            ("kort/pagina-4", 120),
            ("kort/pagina-5", 130),
        ]
        for path, word_count in paths:
            url = Url(
                website_id=website.id,
                normalized_url=f"https://example.com/{path}",
            )
            db.add(url)
            db.flush()
            db.add(_snapshot(url, run, word_count))
        db.flush()

        analyze_contextual_thin_content(
            db,
            website_id=website.id,
            crawl_run_id=run.id,
        )
        db.commit()

        assert db.scalar(select(Issue.id).where(Issue.issue_type == "thin_content")) is None


def test_preserves_nearly_empty_non_functional_page() -> None:
    with SessionLocal() as db:
        website, run = _website_and_run(db)
        url = Url(
            website_id=website.id,
            normalized_url="https://example.com/diensten/lege-pagina",
        )
        db.add(url)
        db.flush()
        db.add(_snapshot(url, run, 12))
        db.flush()

        analyze_contextual_thin_content(
            db,
            website_id=website.id,
            crawl_run_id=run.id,
        )
        db.commit()

        issue = db.scalar(select(Issue).where(Issue.issue_type == "thin_content"))
        assert issue is not None
        assert issue.title == "Nagenoeg lege pagina"


def test_does_not_report_content_with_unknown_indexability() -> None:
    with SessionLocal() as db:
        website, run = _website_and_run(db)
        url = Url(
            website_id=website.id,
            normalized_url="https://example.com/artikelen/onbekend",
        )
        db.add(url)
        db.flush()
        db.add(_snapshot(url, run, 10, is_indexable=None))
        db.flush()

        assert analyze_contextual_thin_content(db, website_id=website.id, crawl_run_id=run.id) == []


def _website_and_run(db):  # type: ignore[no-untyped-def]
    website = Website(
        client=Client(name="Thin context"),
        name="Thin context site",
        base_url="https://example.com/",
    )
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
    return website, run


def _snapshot(
    url: Url,
    run: CrawlRun,
    word_count: int,
    *,
    is_indexable: bool | None = True,
) -> UrlSnapshot:
    return UrlSnapshot(
        url_id=url.id,
        crawl_run_id=run.id,
        requested_url=url.normalized_url,
        final_url=url.normalized_url,
        status_code=200,
        word_count=word_count,
        is_indexable=is_indexable,
        redirect_chain=[],
    )

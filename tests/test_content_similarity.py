from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.issues import Issue, IssueOccurrence
from app.models.website import Website, WebsiteSettings
from app.services.content_similarity import detect_duplicate_content


def _content(unique: str) -> str:
    shared = " ".join(f"gemeenschappelijk{number}" for number in range(120))
    return f"{shared} {unique}"


def test_detects_exact_and_near_duplicate_content_and_resolves_it() -> None:
    with SessionLocal() as db:
        client = Client(name="Content client")
        website = Website(client=client, name="Content site", base_url="https://example.com/")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        urls = [
            Url(
                website_id=website.id,
                normalized_url=f"https://example.com/page-{number}",
                current_status_code=200,
                is_indexable=True,
            )
            for number in range(4)
        ]
        db.add_all(urls)
        db.flush()
        run = _run(db, website.id)
        exact = _content("identiek")
        snapshots = [
            _snapshot(
                urls[0],
                run,
                exact,
                "same-hash",
                title="Gedeelde title",
                meta_description="Gedeelde beschrijving",
            ),
            _snapshot(
                urls[1],
                run,
                exact,
                "same-hash",
                title=" gedeelde   TITLE ",
                meta_description=" gedeelde  BESCHRIJVING ",
            ),
            _snapshot(urls[2], run, _content("variant alpha"), "hash-alpha"),
            _snapshot(urls[3], run, _content("variant beta"), "hash-beta"),
        ]
        db.add_all(snapshots)
        db.flush()

        found = detect_duplicate_content(db, website_id=website.id, crawl_run_id=run.id)
        db.flush()

        assert len(found) == 8
        issues = list(db.scalars(select(Issue).order_by(Issue.issue_type, Issue.url_id)))
        assert [issue.issue_type for issue in issues] == [
            "duplicate_content",
            "duplicate_content",
            "duplicate_meta_description",
            "duplicate_meta_description",
            "duplicate_title",
            "duplicate_title",
            "near_duplicate_content",
            "near_duplicate_content",
        ]
        occurrence = db.scalar(
            select(IssueOccurrence).where(IssueOccurrence.issue_id == issues[0].id)
        )
        assert occurrence is not None
        assert occurrence.evidence["group_size"] == 2

        second_run = _run(db, website.id)
        db.add_all(
            [
                _snapshot(
                    url,
                    second_run,
                    " ".join(f"uniek{index}_{word}" for word in range(160)),
                    f"new-{index}",
                )
                for index, url in enumerate(urls)
            ]
        )
        db.flush()
        assert detect_duplicate_content(db, website_id=website.id, crawl_run_id=second_run.id) == []
        assert {issue.status for issue in issues} == {"resolved"}


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


def _snapshot(  # type: ignore[no-untyped-def]
    url,
    run,
    content: str,
    content_hash: str,
    *,
    title: str | None = None,
    meta_description: str | None = None,
):
    return UrlSnapshot(
        url_id=url.id,
        crawl_run_id=run.id,
        requested_url=url.normalized_url,
        final_url=url.normalized_url,
        status_code=200,
        content_type="text/html",
        redirect_chain=[],
        title=title,
        meta_description=meta_description,
        word_count=len(content.split()),
        main_content=content,
        main_content_hash=content_hash,
        is_indexable=True,
    )

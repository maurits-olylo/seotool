from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.issues import Issue, IssueOccurrence
from app.models.website import Website, WebsiteSettings
from app.services.international_indexation import LANGUAGE_CODE_RE, analyze_international_indexation


def test_hreflang_language_validation_rejects_double_region() -> None:
    assert LANGUAGE_CODE_RE.fullmatch("zh-Hant-TW")
    assert LANGUAGE_CODE_RE.fullmatch("es-419")
    assert not LANGUAGE_CODE_RE.fullmatch("en-US-NL")


def test_detects_multiple_canonicals_and_canonical_chain() -> None:
    with SessionLocal() as db:
        website, run = _website_and_run(db)
        source = _url(db, website.id, "/source")
        middle = _url(db, website.id, "/middle")
        final = _url(db, website.id, "/final")
        db.add_all(
            [
                _snapshot(
                    source,
                    run,
                    canonical="https://example.com/middle",
                    canonical_urls=[
                        "https://example.com/middle",
                        "https://example.com/duplicate",
                    ],
                ),
                _snapshot(middle, run, canonical="https://example.com/final"),
                _snapshot(final, run, canonical="https://example.com/final"),
            ]
        )
        db.flush()

        found = analyze_international_indexation(
            db, website_id=website.id, crawl_run_id=run.id
        )

        assert {issue.issue_type for issue in found} == {
            "canonical_chain",
            "multiple_canonicals",
        }
        occurrence = db.scalar(
            select(IssueOccurrence)
            .join(Issue, Issue.id == IssueOccurrence.issue_id)
            .where(Issue.issue_type == "canonical_chain")
        )
        assert occurrence is not None
        assert occurrence.evidence["path"] == [
            "https://example.com/source",
            "https://example.com/middle",
            "https://example.com/final",
        ]


def test_detects_hreflang_language_return_and_target_conflicts() -> None:
    with SessionLocal() as db:
        website, run = _website_and_run(db)
        source = _url(db, website.id, "/nl")
        target = _url(db, website.id, "/en")
        db.add_all(
            [
                _snapshot(
                    source,
                    run,
                    hreflang_links=[
                        {"language": "nl", "target_url": "https://example.com/nl"},
                        {"language": "english", "target_url": "https://example.com/en"},
                    ],
                ),
                _snapshot(
                    target,
                    run,
                    canonical="https://example.com/en-primary",
                    is_indexable=False,
                    hreflang_links=[],
                ),
            ]
        )
        db.flush()

        found = analyze_international_indexation(
            db, website_id=website.id, crawl_run_id=run.id
        )

        assert {issue.issue_type for issue in found} == {
            "hreflang_invalid_language",
            "hreflang_missing_return",
            "hreflang_target_canonical_mismatch",
            "hreflang_target_noindex",
        }


def test_resolves_disappeared_international_issue() -> None:
    with SessionLocal() as db:
        website, run = _website_and_run(db)
        source = _url(db, website.id, "/source")
        snapshot = _snapshot(
            source,
            run,
            canonical_urls=["https://example.com/a", "https://example.com/b"],
        )
        db.add(snapshot)
        db.flush()
        analyze_international_indexation(db, website_id=website.id, crawl_run_id=run.id)
        issue = db.scalar(select(Issue).where(Issue.issue_type == "multiple_canonicals"))
        assert issue is not None
        snapshot.canonical_urls = []

        analyze_international_indexation(db, website_id=website.id, crawl_run_id=run.id)

        db.refresh(issue)
        assert issue.status == "resolved"


def _website_and_run(db):  # type: ignore[no-untyped-def]
    client = Client(name="International client")
    website = Website(client=client, name="International site", base_url="https://example.com/")
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


def _snapshot(
    url,
    run,
    *,
    canonical=None,
    canonical_urls=None,
    hreflang_links=None,
    is_indexable=True,
):  # type: ignore[no-untyped-def]
    return UrlSnapshot(
        url_id=url.id,
        crawl_run_id=run.id,
        requested_url=url.normalized_url,
        final_url=url.normalized_url,
        status_code=200,
        content_type="text/html",
        redirect_chain=[],
        canonical=canonical,
        canonical_urls=canonical_urls or [],
        hreflang_links=hreflang_links or [],
        is_indexable=is_indexable,
    )

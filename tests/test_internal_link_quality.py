from datetime import date
from unittest.mock import patch

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlLink, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.integrations import SearchConsoleMetric
from app.models.issues import Issue, IssueOccurrence
from app.models.website import Website, WebsiteSettings
from app.services.internal_link_analysis import (
    analyze_generic_anchor_text,
    analyze_internal_link_quality,
    analyze_redirect_source_groups,
)


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

        found = analyze_internal_link_quality(db, website_id=website.id, crawl_run_id=run.id)

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
            analyze_internal_link_quality(db, website_id=website.id, crawl_run_id=second_run.id)
            == []
        )
        assert set(db.scalars(select(Issue.status))) == {"resolved"}


def test_groups_multiple_redirect_links_on_the_source_page() -> None:
    with SessionLocal() as db:
        client = Client(name="Redirect group client")
        website = Website(client=client, name="Redirect site", base_url="https://example.com/")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        source = _url(db, website.id, "/article", depth=1)
        redirects = [
            _url(
                db,
                website.id,
                f"/old-{number}",
                depth=2,
                final_url=f"https://example.com/new-{number}",
            )
            for number in range(2)
        ]
        run = _run(db, website.id)
        for url in (source, *redirects):
            db.add(_snapshot(url, run))
        db.add_all(
            UrlLink(
                crawl_run_id=run.id,
                source_url_id=source.id,
                target_url=redirect.normalized_url,
                target_url_id=redirect.id,
                anchor_text=f"Oude link {number}",
                is_internal=True,
                is_nofollow=False,
            )
            for number, redirect in enumerate(redirects, start=1)
        )
        db.flush()

        with patch(
            "app.services.internal_link_analysis.mark_target_elements_for_targets"
        ) as mark_targets:
            analyze_internal_link_quality(db, website_id=website.id, crawl_run_id=run.id)

        mark_targets.assert_called_once()
        assert mark_targets.call_args.kwargs["target_urls"] == {
            redirect.normalized_url for redirect in redirects
        }

        grouped = db.scalar(
            select(Issue).where(Issue.issue_type == "multiple_redirected_internal_links")
        )
        assert grouped is not None
        assert grouped.url_id == source.id
        assert grouped.title == "2 interne links gaan via een redirect"
        occurrence = db.scalar(
            select(IssueOccurrence).where(IssueOccurrence.issue_id == grouped.id)
        )
        assert occurrence is not None
        assert occurrence.evidence["redirected_link_count"] == 2
        assert occurrence.evidence["redirected_links"][0]["final_url"] == (
            "https://example.com/new-0"
        )

        next_run = _run(db, website.id)
        db.add(
            UrlLink(
                crawl_run_id=next_run.id,
                source_url_id=source.id,
                target_url=redirects[0].normalized_url,
                target_url_id=redirects[0].id,
                anchor_text="Enkele oude link",
                is_internal=True,
                is_nofollow=False,
            )
        )
        db.flush()

        assert (
            analyze_redirect_source_groups(db, website_id=website.id, crawl_run_id=next_run.id)
            == []
        )
        assert grouped.status == "resolved"


def test_does_not_report_a_well_linked_page_at_depth_five() -> None:
    with SessionLocal() as db:
        client = Client(name="Contextual depth client")
        website = Website(client=client, name="Depth site", base_url="https://example.com/")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        deep = _url(db, website.id, "/well-linked-deep-page", depth=5)
        sources = [_url(db, website.id, f"/source-{number}", depth=2) for number in range(12)]
        run = _run(db, website.id)
        for url in (deep, *sources):
            db.add(_snapshot(url, run))
        db.add_all(
            UrlLink(
                crawl_run_id=run.id,
                source_url_id=source.id,
                target_url=deep.normalized_url,
                target_url_id=deep.id,
                anchor_text="Relevante verdieping",
                is_internal=True,
                is_nofollow=False,
            )
            for source in sources
        )
        db.flush()

        found = analyze_internal_link_quality(db, website_id=website.id, crawl_run_id=run.id)

        assert all(issue.issue_type != "deep_page" for issue in found)
        assert db.scalar(select(Issue).where(Issue.issue_type == "deep_page")) is None


def test_groups_generic_internal_anchor_text_for_the_website() -> None:
    with SessionLocal() as db:
        client = Client(name="Anchor quality client")
        website = Website(client=client, name="Anchor site", base_url="https://example.com/")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        sources = [
            _url(db, website.id, "/article-one", depth=1),
            _url(db, website.id, "/article-two", depth=1),
        ]
        working_target = _url(db, website.id, "/working", depth=2)
        broken_target = _url(db, website.id, "/missing", depth=2)
        broken_target.current_status_code = 404
        run = _run(db, website.id)
        db.add_all(
            [
                UrlLink(
                    crawl_run_id=run.id,
                    source_url_id=sources[0].id,
                    target_url=working_target.normalized_url,
                    target_url_id=working_target.id,
                    anchor_text="Lees meer",
                    is_internal=True,
                    is_nofollow=False,
                ),
                UrlLink(
                    crawl_run_id=run.id,
                    source_url_id=sources[1].id,
                    target_url=broken_target.normalized_url,
                    target_url_id=broken_target.id,
                    anchor_text="Klik hier",
                    is_internal=True,
                    is_nofollow=False,
                ),
                UrlLink(
                    crawl_run_id=run.id,
                    source_url_id=sources[1].id,
                    target_url=working_target.normalized_url,
                    target_url_id=working_target.id,
                    anchor_text="Lees het volledige onderzoeksrapport",
                    is_internal=True,
                    is_nofollow=False,
                ),
            ]
        )
        db.flush()

        found = analyze_generic_anchor_text(
            db,
            website_id=website.id,
            crawl_run_id=run.id,
        )

        assert len(found) == 1
        assert found[0].issue_type == "generic_internal_anchor_text"
        assert found[0].url_id is None
        occurrence = db.scalar(
            select(IssueOccurrence).where(IssueOccurrence.issue_id == found[0].id)
        )
        assert occurrence is not None
        assert occurrence.evidence["affected_source_pages"] == 2
        assert occurrence.evidence["generic_link_count"] == 2
        assert occurrence.evidence["broken_link_count"] == 1
        assert len(occurrence.evidence["generic_links"]) == 2


def test_does_not_report_deep_discovery_only_query_variant() -> None:
    with SessionLocal() as db:
        client = Client(name="Discovery depth client")
        website = Website(client=client, name="Jobs", base_url="https://example.com/")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        variant = _url(db, website.id, "/jobs?filter=seo", depth=7)
        run = _run(db, website.id)
        snapshot = _snapshot(variant, run)
        snapshot.canonical = "https://example.com/jobs"
        db.add(snapshot)
        db.flush()

        found = analyze_internal_link_quality(
            db,
            website_id=website.id,
            crawl_run_id=run.id,
        )

        assert found == []
        assert db.scalar(select(Issue)) is None


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

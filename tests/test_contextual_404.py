from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlLink
from app.models.discovery import CrawlJob, Url, UrlSource
from app.models.issues import Issue, IssueOccurrence
from app.models.website import Website, WebsiteSettings
from app.services.contextual_404 import classify_404_issues


def test_classifies_linked_and_sitemap_404s_exclusively() -> None:
    with SessionLocal() as db:
        client = Client(name="404 client")
        website = Website(client=client, name="404 site", base_url="https://example.com")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        source = Url(website_id=website.id, normalized_url="https://example.com/")
        linked = Url(
            website_id=website.id,
            normalized_url="https://example.com/linked",
            current_status_code=404,
        )
        sitemap = Url(
            website_id=website.id,
            normalized_url="https://example.com/sitemap-only",
            current_status_code=404,
        )
        db.add_all([source, linked, sitemap])
        db.flush()
        db.add(UrlSource(url_id=sitemap.id, source_type="sitemap", source_url="sitemap.xml"))
        job = CrawlJob(website_id=website.id, job_type="full_site_crawl")
        db.add(job)
        db.flush()
        run = CrawlRun(crawl_job_id=job.id, website_id=website.id, crawl_type="full_site_crawl")
        db.add(run)
        db.flush()
        db.add(
            UrlLink(
                crawl_run_id=run.id,
                source_url_id=source.id,
                target_url=linked.normalized_url,
                target_url_id=linked.id,
                is_internal=True,
                is_nofollow=False,
            )
        )
        db.add(
            UrlLink(
                crawl_run_id=run.id,
                source_url_id=linked.id,
                target_url=linked.normalized_url,
                target_url_id=linked.id,
                anchor_text="Zelfverwijzing op foutpagina",
                is_internal=True,
                is_nofollow=False,
            )
        )
        db.add(
            Issue(
                website_id=website.id,
                url_id=linked.id,
                issue_type="http_404",
                category="reachability",
                severity="high",
                title="404",
                description="404",
                recommended_action="Fix",
            )
        )
        db.flush()

        classify_404_issues(db, website_id=website.id, crawl_run_id=run.id)

        issues = list(db.scalars(select(Issue).order_by(Issue.issue_type)))
        states = {(issue.url_id, issue.issue_type): issue.status for issue in issues}
        assert states[(linked.id, "http_404")] == "resolved"
        assert states[(linked.id, "internally_linked_404")] == "new"
        assert states[(sitemap.id, "sitemap_404")] == "new"
        linked_issue = db.scalar(
            select(Issue).where(
                Issue.url_id == linked.id,
                Issue.issue_type == "internally_linked_404",
            )
        )
        assert linked_issue is not None
        occurrence = db.scalar(
            select(IssueOccurrence).where(IssueOccurrence.issue_id == linked_issue.id)
        )
        assert occurrence is not None
        assert occurrence.evidence["incoming_internal_links"] == 1


def test_groups_multiple_broken_links_on_one_source_page() -> None:
    with SessionLocal() as db:
        client = Client(name="Grouped 404 client")
        website = Website(client=client, name="Grouped site", base_url="https://example.com")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        source = Url(website_id=website.id, normalized_url="https://example.com/article")
        targets = [
            Url(
                website_id=website.id,
                normalized_url=f"https://example.com/missing-{number}",
                current_status_code=404,
            )
            for number in range(3)
        ]
        db.add_all([source, *targets])
        db.flush()
        job = CrawlJob(website_id=website.id, job_type="full_site_crawl")
        db.add(job)
        db.flush()
        run = CrawlRun(crawl_job_id=job.id, website_id=website.id, crawl_type="full_site_crawl")
        db.add(run)
        db.flush()
        db.add_all(
            [
                UrlLink(
                    crawl_run_id=run.id,
                    source_url_id=source.id,
                    target_url=target.normalized_url,
                    target_url_id=target.id,
                    anchor_text=f"Link {number}",
                    is_internal=True,
                    is_nofollow=False,
                )
                for number, target in enumerate(targets, start=1)
            ]
        )
        db.flush()

        classify_404_issues(db, website_id=website.id, crawl_run_id=run.id)

        grouped = db.scalar(
            select(Issue).where(
                Issue.url_id == source.id,
                Issue.issue_type == "multiple_broken_internal_links",
            )
        )
        assert grouped is not None
        assert grouped.title == "3 dode interne links op deze pagina"
        assert grouped.status == "new"
        occurrence = db.scalar(
            select(IssueOccurrence).where(IssueOccurrence.issue_id == grouped.id)
        )
        assert occurrence is not None
        assert occurrence.evidence["broken_link_count"] == 3
        assert occurrence.evidence["broken_links"][1] == {
            "target_url": "https://example.com/missing-1",
            "anchor_text": "Link 2",
            "status_code": 404,
        }

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
        db.add(
            UrlLink(
                crawl_run_id=next_run.id,
                source_url_id=source.id,
                target_url=targets[0].normalized_url,
                target_url_id=targets[0].id,
                anchor_text="Link 1",
                is_internal=True,
                is_nofollow=False,
            )
        )
        db.flush()

        classify_404_issues(db, website_id=website.id, crawl_run_id=next_run.id)

        db.refresh(grouped)
        assert grouped.status == "resolved"


def test_groups_paginated_404_urls_as_one_pattern() -> None:
    with SessionLocal() as db:
        client = Client(name="Pagination client")
        website = Website(client=client, name="Pagination site", base_url="https://human.test")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        urls = [
            Url(
                website_id=website.id,
                normalized_url=f"https://human.test/durf/artikelen?page={number}",
                current_status_code=404,
            )
            for number in (3, 4, 5)
        ]
        db.add_all(urls)
        db.flush()
        run = _crawl_run(db, website.id)

        classify_404_issues(db, website_id=website.id, crawl_run_id=run.id)

        issue = db.scalar(
            select(Issue).where(
                Issue.website_id == website.id,
                Issue.url_id.is_(None),
                Issue.issue_type == "patterned_404_urls",
            )
        )
        assert issue is not None
        assert issue.title == "3 404-URL's vormen 1 herkenbaar patroon"
        occurrence = db.scalar(
            select(IssueOccurrence).where(IssueOccurrence.issue_id == issue.id)
        )
        assert occurrence is not None
        assert occurrence.evidence["pattern_count"] == 1
        assert occurrence.evidence["patterns"][0]["pattern"] == "/durf/artikelen?page=*"
        assert occurrence.evidence["patterns"][0]["pattern_type"] == "pagination"


def _crawl_run(db, website_id):  # type: ignore[no-untyped-def]
    job = CrawlJob(website_id=website_id, job_type="full_site_crawl")
    db.add(job)
    db.flush()
    run = CrawlRun(crawl_job_id=job.id, website_id=website_id, crawl_type="full_site_crawl")
    db.add(run)
    db.flush()
    return run

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun
from app.models.discovery import CrawlJob, Url
from app.models.issues import Issue, IssueOccurrence
from app.models.website import Website, WebsiteSettings
from app.services.template_issue_analysis import analyze_template_issue_clusters


def test_groups_repeated_template_signals_and_resolves_when_they_disappear() -> None:
    with SessionLocal() as db:
        client = Client(name="Template client")
        website = Website(client=client, name="Template site", base_url="https://example.com")
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
        legacy = Issue(
            website_id=website.id,
            url_id=None,
            issue_type="template_signal_clusters",
            category="onpage",
            severity="medium",
            title="Oude gecombineerde diagnose",
            description="Wordt vervangen.",
            recommended_action="Controleer alle clusters.",
        )
        db.add(legacy)
        db.flush()

        for number in range(10):
            url = Url(
                website_id=website.id,
                normalized_url=f"https://example.com/articles/item-{number}",
            )
            db.add(url)
            db.flush()
            issue = Issue(
                website_id=website.id,
                url_id=url.id,
                issue_type="deep_page",
                category="internal_links",
                severity="low",
                title="Pagina ligt diep",
                description="Controleer de interne structuur.",
                recommended_action="Controleer de template.",
            )
            db.add(issue)
            db.flush()
            db.add(
                IssueOccurrence(
                    issue_id=issue.id,
                    crawl_run_id=run.id,
                    evidence={"crawl_depth": 5, "related_urls": ["https://example.com/large"] * 50},
                )
            )
        db.flush()

        found = analyze_template_issue_clusters(
            db, website_id=website.id, crawl_run_id=run.id
        )
        db.flush()

        assert len(found) == 1
        assert found[0].issue_type == "deep_page_clusters"
        assert legacy.status == "resolved"
        occurrence = db.scalar(
            select(IssueOccurrence).where(IssueOccurrence.issue_id == found[0].id)
        )
        assert occurrence is not None
        assert occurrence.evidence["affected_signal_count"] == 10
        assert occurrence.evidence["cluster_count"] == 1
        cluster = occurrence.evidence["clusters"][0]
        assert cluster["cluster_key"] == "/articles/item-{n}/*"
        assert cluster["sample_evidence"] == {"crawl_depth": 5}

        for issue in db.scalars(
            select(Issue).where(Issue.url_id.is_not(None))
        ):
            issue.status = "resolved"
        db.flush()

        assert analyze_template_issue_clusters(
            db, website_id=website.id, crawl_run_id=run.id
        ) == []
        assert found[0].status == "resolved"


def test_does_not_group_duplicate_metadata_without_the_shared_value() -> None:
    with SessionLocal() as db:
        client = Client(name="Missing evidence client")
        website = Website(client=client, name="Missing evidence", base_url="https://example.org")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        job = CrawlJob(website_id=website.id, job_type="full_site_crawl")
        db.add(job)
        db.flush()
        run = CrawlRun(crawl_job_id=job.id, website_id=website.id, crawl_type="full_site_crawl")
        db.add(run)
        db.flush()
        for number in range(3):
            url = Url(website_id=website.id, normalized_url=f"https://example.org/news/{number}")
            db.add(url)
            db.flush()
            db.add(
                Issue(
                    website_id=website.id,
                    url_id=url.id,
                    issue_type="duplicate_title",
                    category="onpage",
                    severity="medium",
                    title="Dubbele title",
                    description="Geen bewijswaarde beschikbaar.",
                    recommended_action="Controleer dit.",
                )
            )
        db.flush()

        assert analyze_template_issue_clusters(
            db, website_id=website.id, crawl_run_id=run.id
        ) == []


def test_groups_small_child_families_at_the_shared_parent_level() -> None:
    with SessionLocal() as db:
        client = Client(name="Parent client")
        website = Website(client=client, name="Parent site", base_url="https://parent.example")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        job = CrawlJob(website_id=website.id, job_type="full_site_crawl")
        db.add(job)
        db.flush()
        run = CrawlRun(crawl_job_id=job.id, website_id=website.id, crawl_type="full_site_crawl")
        db.add(run)
        db.flush()

        for suffix in "abcdefghij":
            url = Url(
                website_id=website.id,
                normalized_url=f"https://parent.example/guides/topic-{suffix}/page",
            )
            db.add(url)
            db.flush()
            issue = Issue(
                website_id=website.id,
                url_id=url.id,
                issue_type="deep_page",
                category="internal_links",
                severity="low",
                title="Diepe pagina",
                description="Controleer de structuur.",
                recommended_action="Voeg een link toe.",
            )
            db.add(issue)
            db.flush()
            db.add(
                IssueOccurrence(
                    issue_id=issue.id,
                    crawl_run_id=run.id,
                    evidence={"crawl_depth": 5},
                )
            )
        db.flush()

        diagnosis = analyze_template_issue_clusters(
            db, website_id=website.id, crawl_run_id=run.id
        )[0]
        db.flush()
        occurrence = db.scalar(
            select(IssueOccurrence).where(IssueOccurrence.issue_id == diagnosis.id)
        )

        assert occurrence is not None
        assert occurrence.evidence["clusters"][0]["cluster_key"] == "/guides/*"
        assert occurrence.evidence["affected_signal_count"] == 10


def test_groups_an_exact_duplicate_pair() -> None:
    with SessionLocal() as db:
        client = Client(name="Pair client")
        website = Website(client=client, name="Pair site", base_url="https://pair.example")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        job = CrawlJob(website_id=website.id, job_type="full_site_crawl")
        db.add(job)
        db.flush()
        run = CrawlRun(crawl_job_id=job.id, website_id=website.id, crawl_type="full_site_crawl")
        db.add(run)
        db.flush()
        for suffix in ("one", "two"):
            url = Url(website_id=website.id, normalized_url=f"https://pair.example/{suffix}")
            db.add(url)
            db.flush()
            issue = Issue(
                website_id=website.id,
                url_id=url.id,
                issue_type="duplicate_title",
                category="onpage",
                severity="medium",
                title="Dubbele title",
                description="Dezelfde title.",
                recommended_action="Maak de title onderscheidend.",
            )
            db.add(issue)
            db.flush()
            db.add(
                IssueOccurrence(
                    issue_id=issue.id,
                    crawl_run_id=run.id,
                    evidence={"value": "Gedeelde title"},
                )
            )
        db.flush()

        diagnosis = analyze_template_issue_clusters(
            db, website_id=website.id, crawl_run_id=run.id
        )[0]
        db.flush()
        occurrence = db.scalar(
            select(IssueOccurrence).where(IssueOccurrence.issue_id == diagnosis.id)
        )

        assert occurrence is not None
        assert diagnosis.issue_type == "duplicate_title_clusters"
        assert occurrence.evidence["affected_signal_count"] == 2
        assert occurrence.evidence["clusters"][0]["cluster_key"] == "value:Gedeelde title"


def test_groups_missing_job_schema_as_one_vacancy_template_action() -> None:
    with SessionLocal() as db:
        client = Client(name="Vacancy template client")
        website = Website(
            client=client,
            name="Vacancy site",
            base_url="https://jobs.example",
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
        for number in range(5):
            url = Url(
                website_id=website.id,
                normalized_url=f"https://jobs.example/vacatures/rol-{number}",
            )
            db.add(url)
            db.flush()
            issue = Issue(
                website_id=website.id,
                url_id=url.id,
                issue_type="job_posting_schema_missing",
                category="structured_data",
                severity="high",
                title="Vacature mist JobPosting-schema",
                description="Geen schema gevonden.",
                recommended_action="Voeg schema toe in het vacaturetemplate.",
            )
            db.add(issue)
            db.flush()
            db.add(
                IssueOccurrence(
                    issue_id=issue.id,
                    crawl_run_id=run.id,
                    evidence={"source": "url_and_page_text"},
                )
            )
        db.flush()

        diagnosis = analyze_template_issue_clusters(
            db, website_id=website.id, crawl_run_id=run.id
        )[0]
        db.flush()
        occurrence = db.scalar(
            select(IssueOccurrence).where(IssueOccurrence.issue_id == diagnosis.id)
        )

        assert occurrence is not None
        cluster = occurrence.evidence["clusters"][0]
        assert cluster["issue_type"] == "job_posting_schema_missing"
        assert cluster["url_count"] == 5
        assert cluster["sample_evidence"] == {"source": "url_and_page_text"}


def test_groups_an_orphan_pair_and_keeps_it_separate_from_other_types() -> None:
    with SessionLocal() as db:
        client = Client(name="Orphan pair client")
        website = Website(client=client, name="Orphan pair", base_url="https://orphan.example")
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
        for number in range(2):
            url = Url(
                website_id=website.id,
                normalized_url=f"https://orphan.example/programme/page-{number}",
            )
            db.add(url)
            db.flush()
            issue = Issue(
                website_id=website.id,
                url_id=url.id,
                issue_type="orphan_page",
                category="internal_links",
                severity="medium",
                title="Orphan page",
                description="Niet intern bereikbaar.",
                recommended_action="Controleer de interne route.",
            )
            db.add(issue)
            db.flush()
            db.add(
                IssueOccurrence(
                    issue_id=issue.id,
                    crawl_run_id=run.id,
                    evidence={"crawl_depth": None},
                )
            )
        db.flush()

        found = analyze_template_issue_clusters(
            db, website_id=website.id, crawl_run_id=run.id
        )

        assert [issue.issue_type for issue in found] == ["orphan_page_clusters"]
        assert found[0].category == "internal_links"

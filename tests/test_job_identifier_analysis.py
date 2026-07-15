from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.issues import Issue, IssueOccurrence
from app.models.website import Website, WebsiteSettings
from app.services.job_identifier_analysis import analyze_job_identifier_risk


def _content(unique: str) -> str:
    shared = " ".join(f"vacaturetekst{number}" for number in range(120))
    return f"{shared} {unique}"


def test_similar_vacancies_without_identifier_get_contextual_risk() -> None:
    with SessionLocal() as db:
        client = Client(name="Vacatureklant")
        website = Website(client=client, name="Vacatures", base_url="https://example.com/")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        urls = [
            Url(
                website_id=website.id,
                normalized_url=f"https://example.com/vacatures/rol-{number}",
                current_status_code=200,
                is_indexable=True,
            )
            for number in range(6)
        ]
        db.add_all(urls)
        db.flush()
        run = _run(db, website.id)
        for index, url in enumerate(urls):
            schema = {
                "@type": "JobPosting",
                "title": f"Rol {index}",
                "description": "Vacature",
                "datePosted": "2026-01-01",
                "hiringOrganization": {"name": "Werkgever"},
            }
            if index == 5:
                schema["identifier"] = {"value": "rol-5"}
            content = _content(f"unieke rol {index}")
            db.add(
                UrlSnapshot(
                    url_id=url.id,
                    crawl_run_id=run.id,
                    requested_url=url.normalized_url,
                    final_url=url.normalized_url,
                    status_code=200,
                    content_type="text/html",
                    redirect_chain=[],
                    word_count=len(content.split()),
                    main_content=content,
                    main_content_hash=f"hash-{index}",
                    schema_types=["JobPosting"],
                    schema_data=[schema],
                    is_indexable=True,
                )
            )
        db.flush()

        found = analyze_job_identifier_risk(
            db, website_id=website.id, crawl_run_id=run.id
        )
        db.flush()

        assert len(found) == 5
        issues = list(
            db.scalars(
                select(Issue).where(
                    Issue.issue_type == "job_posting_identifier_collision_risk"
                )
            )
        )
        assert len(issues) == 5
        assert {issue.severity for issue in issues} == {"medium"}
        occurrence = db.scalar(
            select(IssueOccurrence).where(IssueOccurrence.issue_id == issues[0].id)
        )
        assert occurrence is not None
        assert occurrence.evidence["group_size"] == 5
        assert len(occurrence.evidence["related_urls"]) == 4


def test_single_vacancy_without_identifier_is_only_an_optimization() -> None:
    with SessionLocal() as db:
        client = Client(name="Enkele vacature")
        website = Website(client=client, name="Vacature", base_url="https://single.example/")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        url = Url(
            website_id=website.id,
            normalized_url="https://single.example/vacatures/seo",
            current_status_code=200,
            is_indexable=True,
        )
        db.add(url)
        db.flush()
        run = _run(db, website.id)
        content = _content("zelfstandige vacature")
        db.add(
            UrlSnapshot(
                url_id=url.id,
                crawl_run_id=run.id,
                requested_url=url.normalized_url,
                final_url=url.normalized_url,
                status_code=200,
                content_type="text/html",
                redirect_chain=[],
                word_count=len(content.split()),
                main_content=content,
                schema_types=["JobPosting"],
                schema_data=[{"@type": "JobPosting", "title": "SEO"}],
                is_indexable=True,
            )
        )
        db.flush()

        assert analyze_job_identifier_risk(
            db, website_id=website.id, crawl_run_id=run.id
        ) == []
        assert db.scalar(select(Issue)) is None


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

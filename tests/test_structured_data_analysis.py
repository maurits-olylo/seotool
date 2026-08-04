from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.issues import Issue
from app.models.website import Website, WebsiteSettings
from app.services.structured_data_analysis import (
    analyze_breadcrumb_consistency,
    analyze_contextual_structured_data,
    contextual_schema_nodes,
    schema_image_urls,
)


def test_reports_breadcrumb_gap_only_when_site_consistently_uses_schema() -> None:
    with SessionLocal() as db:
        client = Client(name="Breadcrumb client")
        website = Website(client=client, name="Breadcrumb site", base_url="https://example.com/")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        run = _run(db, website.id)
        urls = [_url(db, website.id, number) for number in range(6)]
        for index, url in enumerate(urls):
            db.add(_snapshot(url, run, has_breadcrumb=index < 3))
        db.flush()

        found = analyze_breadcrumb_consistency(db, website_id=website.id, crawl_run_id=run.id)

        assert len(found) == 3
        assert {issue.issue_type for issue in found} == {"missing_breadcrumb_schema"}
        assert {issue.url_id for issue in found} == {url.id for url in urls[3:]}

        second_run = _run(db, website.id)
        for url in urls:
            db.add(_snapshot(url, second_run, has_breadcrumb=True))
        db.flush()

        assert (
            analyze_breadcrumb_consistency(db, website_id=website.id, crawl_run_id=second_run.id)
            == []
        )
        assert set(db.scalars(select(Issue.status))) == {"resolved"}


def test_validates_only_recognized_top_level_page_schema() -> None:
    values = [
        {
            "@type": "Product",
            "name": "Groene stoel",
            "image": "https://example.com/stoel.jpg",
            "offers": {"@type": "Offer", "price": "99"},
            "brand": {"@type": "Organization", "name": "Stoelenmerk"},
        }
    ]

    nodes = contextual_schema_nodes(values)

    assert [schema_type for schema_type, _node in nodes] == ["Product"]
    assert schema_image_urls(values) == ["https://example.com/stoel.jpg"]


def test_reports_missing_fields_and_visible_content_mismatch_contextually() -> None:
    with SessionLocal() as db:
        website = Website(
            client=Client(name="Structured client"),
            name="Structured site",
            base_url="https://example.com/",
        )
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        run = _run(db, website.id)
        url = _url(db, website.id, 20)
        db.add(
            UrlSnapshot(
                url_id=url.id,
                crawl_run_id=run.id,
                requested_url=url.normalized_url,
                final_url=url.normalized_url,
                status_code=200,
                content_type="text/html",
                redirect_chain=[],
                title="Andere productnaam",
                headings={"h1": ["Andere productnaam"]},
                main_content="Beschrijving van een ander product.",
                schema_types=["Product"],
                schema_data=[{"@type": "Product", "name": "Groene stoel"}],
                is_indexable=True,
            )
        )
        db.flush()

        found = analyze_contextual_structured_data(
            db, website_id=website.id, crawl_run_id=run.id
        )

        assert {issue.issue_type for issue in found} == {
            "structured_data_required_fields_missing",
            "structured_data_visible_content_mismatch",
        }
        missing = next(
            issue
            for issue in found
            if issue.issue_type == "structured_data_required_fields_missing"
        )
        evidence = db.scalar(
            select(Issue).where(Issue.id == missing.id)
        )
        assert evidence is not None


def test_reports_only_measured_broken_internal_schema_images() -> None:
    with SessionLocal() as db:
        website = Website(
            client=Client(name="Schema image client"),
            name="Schema image site",
            base_url="https://example.com/",
        )
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        broken = Url(
            website_id=website.id,
            normalized_url="https://example.com/broken.jpg",
            current_status_code=404,
            is_active=True,
        )
        db.add(broken)
        run = _run(db, website.id)
        page = _url(db, website.id, 21)
        db.add(
            UrlSnapshot(
                url_id=page.id,
                crawl_run_id=run.id,
                requested_url=page.normalized_url,
                final_url=page.normalized_url,
                status_code=200,
                content_type="text/html",
                redirect_chain=[],
                title="Nieuwsbericht",
                headings={"h1": ["Nieuwsbericht"]},
                main_content="Nieuwsbericht met volledige zichtbare inhoud.",
                schema_types=["Article"],
                schema_data=[
                    {
                        "@type": "Article",
                        "headline": "Nieuwsbericht",
                        "datePublished": "2026-08-04",
                        "image": "https://example.com/broken.jpg",
                    }
                ],
                is_indexable=True,
            )
        )
        db.flush()

        found = analyze_contextual_structured_data(
            db, website_id=website.id, crawl_run_id=run.id
        )

        assert [issue.issue_type for issue in found] == [
            "structured_data_image_unreachable"
        ]


def test_complete_contextual_schema_produces_no_generic_missing_schema_issue() -> None:
    with SessionLocal() as db:
        website = Website(
            client=Client(name="Complete schema client"),
            name="Complete schema site",
            base_url="https://example.com/",
        )
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        run = _run(db, website.id)
        url = _url(db, website.id, 22)
        db.add(
            UrlSnapshot(
                url_id=url.id,
                crawl_run_id=run.id,
                requested_url=url.normalized_url,
                final_url=url.normalized_url,
                status_code=200,
                content_type="text/html",
                redirect_chain=[],
                title="SEO evenement",
                headings={"h1": ["SEO evenement"]},
                main_content="SEO evenement in Utrecht.",
                schema_types=["Event"],
                schema_data=[
                    {
                        "@type": "Event",
                        "name": "SEO evenement",
                        "startDate": "2026-09-01",
                        "location": {"@type": "Place", "name": "Utrecht"},
                    }
                ],
                is_indexable=True,
            )
        )
        db.flush()

        assert (
            analyze_contextual_structured_data(
                db, website_id=website.id, crawl_run_id=run.id
            )
            == []
        )


def _url(db, website_id, number):  # type: ignore[no-untyped-def]
    url = Url(
        website_id=website_id,
        normalized_url=f"https://example.com/category/page-{number}",
        current_status_code=200,
        is_active=True,
        is_indexable=True,
        crawl_depth=2,
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


def _snapshot(url, run, *, has_breadcrumb):  # type: ignore[no-untyped-def]
    return UrlSnapshot(
        url_id=url.id,
        crawl_run_id=run.id,
        requested_url=url.normalized_url,
        final_url=url.normalized_url,
        status_code=200,
        content_type="text/html",
        redirect_chain=[],
        schema_types=["BreadcrumbList"] if has_breadcrumb else [],
        schema_data=[],
        is_indexable=True,
    )

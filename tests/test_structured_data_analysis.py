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

        found = analyze_contextual_structured_data(db, website_id=website.id, crawl_run_id=run.id)

        assert {issue.issue_type for issue in found} == {
            "structured_data_required_fields_missing",
            "structured_data_visible_content_mismatch",
        }
        missing = next(
            issue
            for issue in found
            if issue.issue_type == "structured_data_required_fields_missing"
        )
        evidence = db.scalar(select(Issue).where(Issue.id == missing.id))
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

        found = analyze_contextual_structured_data(db, website_id=website.id, crawl_run_id=run.id)

        assert [issue.issue_type for issue in found] == ["structured_data_image_unreachable"]


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
            analyze_contextual_structured_data(db, website_id=website.id, crawl_run_id=run.id) == []
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


def test_publisher_is_not_compared_to_page_title_but_other_checks_remain() -> None:
    from app.services.structured_data_analysis import _contextual_schema_signals

    snapshot = UrlSnapshot(
        status_code=200, title="Artikelen", headings={}, main_content="Overzicht"
    )
    nodes = contextual_schema_nodes(
        [
            {
                "@graph": [
                    {"@type": "Organization", "name": "HUMAN - Radicaal menselijk"},
                    {
                        "@type": "Article",
                        "headline": "Artikelen",
                        "image": "https://example.com/img.jpg",
                        "datePublished": "2026-09-01",
                    },
                ]
            }
        ]
    )
    signals = _contextual_schema_signals(snapshot, nodes, {})
    assert {signal.issue_type for signal in signals} == {"structured_data_required_fields_missing"}
    assert signals[0].evidence["schemas"][0]["schema_type"] == "Organization"


def test_schema_comparison_normalizes_typography_and_requires_review() -> None:
    from app.services.structured_data_analysis import _contextual_schema_signals

    snapshot = UrlSnapshot(status_code=200, title="Groene — stoel", headings={}, main_content="")
    nodes = [
        ("Product", {"name": "GROENE  stoel", "image": "/image.jpg", "offers": {"price": "20"}})
    ]
    assert _contextual_schema_signals(snapshot, nodes, {}) == []
    nodes[0][1]["name"] = "Blauwe tafel"
    signals = _contextual_schema_signals(snapshot, nodes, {})
    assert len(signals) == 1
    assert signals[0].confidence == "low"
    assert signals[0].evidence["decision_required"] is True
    snapshot.title = ""
    assert _contextual_schema_signals(snapshot, nodes, {}) == []


def test_legacy_schema_alert_is_reviewed_not_counted_as_website_repair() -> None:
    with SessionLocal() as db:
        website = Website(
            client=Client(name="Legacy schema"), name="Legacy", base_url="https://example.com/"
        )
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        run = _run(db, website.id)
        url = _url(db, website.id, 55)
        db.add(
            UrlSnapshot(
                url_id=url.id,
                crawl_run_id=run.id,
                requested_url=url.normalized_url,
                final_url=url.normalized_url,
                status_code=200,
                title="Artikelen",
                headings={},
                main_content="Overzicht",
                schema_data=[
                    {"@type": "Organization", "name": "Publisher", "url": "https://example.com/"}
                ],
            )
        )
        issue = Issue(
            website_id=website.id,
            url_id=url.id,
            issue_type="structured_data_visible_content_mismatch",
            category="structured_data",
            severity="medium",
            title="Old",
            description="Old",
            recommended_action="Old",
        )
        db.add(issue)
        db.flush()
        analyze_contextual_structured_data(db, website_id=website.id, crawl_run_id=run.id)
        assert issue.status == "review"
        assert issue.resolved_at is None


def test_narrow_headline_variants_match_production_examples_without_fuzzy_approval() -> None:
    from app.services.structured_data_analysis import _headline_variant_matches

    examples = [
        ("Kijk 3LAB: Sjiek de friemel", "3LAB: Sjiek de Friemel", "3LAB: Sjiek de Friemel", True),
        ("Kijk It will rain bij HUMAN", "It will rain", "3LAB: It will rain", True),
        (
            "Kijk Tessel in Cyberspace",
            "Kijk de onlineserie 'Tessel in cyberspace'",
            "3LAB: Tessel in Cyberspace",
            True,
        ),
        ("Kijk Filmlab: Merhamet op NPO 3", "Merhamet", "3LAB: Merhamet", False),
        (
            "Kijk 2Doc Kort: Blauw Licht - Herinneringen van een Ambulancebroeder",
            "Blauw Licht",
            "Blauw licht",
            False,
        ),
        (
            "Update hoofdpersonen Gewoon liefde - Human - 2Doc",
            "We kregen reacties uit de hele wereld",
            "We kregen reacties uit de hele wereld",
            False,
        ),
        ("Kijk It will rain niet", "It will rain", "It will rain", False),
        ("Kijk It will rain morgen", "It will rain", "It will rain", False),
        ("Kijk It will rain bij ANDER", "It will rain", "It will rain", False),
        ("Kijk de film", "de film", "de film", False),
        ("Kijk It will rainfall", "It will rain", "It will rain", False),
    ]
    for headline, title, h1, expected in examples:
        snapshot = UrlSnapshot(title=title + " | HUMAN - Radicaal menselijk", headings={"h1": [h1]})
        assert _headline_variant_matches(snapshot, headline) is expected, headline


def test_headline_variants_do_not_disable_other_schema_checks_or_product_names() -> None:
    from app.services.structured_data_analysis import _contextual_schema_signals

    snapshot = UrlSnapshot(
        status_code=200,
        title="It will rain | HUMAN",
        headings={"h1": ["It will rain"]},
        main_content="Beschrijving",
    )
    article = [("Article", {"headline": "Kijk It will rain bij HUMAN"})]
    signals = _contextual_schema_signals(snapshot, article, {})
    assert {s.issue_type for s in signals} == {"structured_data_required_fields_missing"}
    product = [("Product", {"name": "Kijk It will rain bij HUMAN"})]
    signals = _contextual_schema_signals(snapshot, product, {})
    assert "structured_data_visible_content_mismatch" in {s.issue_type for s in signals}
    mismatch = next(
        s for s in signals if s.issue_type == "structured_data_visible_content_mismatch"
    )
    assert mismatch.evidence["comparison_version"] == 3


def test_version_two_headline_alert_becomes_review_not_repair_after_variant_rule() -> None:
    from app.models.issues import IssueOccurrence

    with SessionLocal() as db:
        website = Website(
            client=Client(name="Variant"), name="Variant", base_url="https://example.com/"
        )
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        run = _run(db, website.id)
        url = _url(db, website.id, 77)
        snapshot = UrlSnapshot(
            url_id=url.id,
            crawl_run_id=run.id,
            requested_url=url.normalized_url,
            status_code=200,
            title="It will rain | HUMAN",
            headings={"h1": ["It will rain"]},
            main_content="Film",
            schema_data=[
                {
                    "@type": "Article",
                    "headline": "Kijk It will rain bij HUMAN",
                    "image": "https://example.com/image.jpg",
                    "datePublished": "2026-09-01",
                }
            ],
        )
        issue = Issue(
            website_id=website.id,
            url_id=url.id,
            issue_type="structured_data_visible_content_mismatch",
            category="structured_data",
            severity="medium",
            title="Old",
            description="Old",
            recommended_action="Old",
        )
        db.add_all([snapshot, issue])
        db.flush()
        occurrence = IssueOccurrence(
            issue_id=issue.id,
            crawl_run_id=run.id,
            snapshot_id=snapshot.id,
            evidence={
                "comparison_version": 2,
                "mismatches": [
                    {
                        "schema_type": "Article",
                        "field": "headline",
                        "schema_value": "Kijk It will rain bij HUMAN",
                    }
                ],
            },
        )
        db.add(occurrence)
        db.flush()
        analyze_contextual_structured_data(db, website_id=website.id, crawl_run_id=run.id)
        assert issue.status == "review"
        assert issue.resolved_at is None and issue.verified_at is None
        assert occurrence.evidence["comparison_version"] == 2

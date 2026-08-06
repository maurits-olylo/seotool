from datetime import UTC, date, datetime

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.content_analysis import QueryContentClassification, UrlContentClassification
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.integrations import SearchConsoleQueryMetric
from app.models.website import Website, WebsiteSettings
from app.services.content_analysis import (
    CLASSIFICATION_VERSION,
    analyze_website_content,
    classify_page,
    classify_query,
)


def test_query_rules_are_explainable_and_contextual() -> None:
    informational = classify_query("Hoe werkt een warmtepomp?")
    assert informational.search_intent == "informational"
    assert informational.journey_stage == "understand"
    assert informational.content_role == "attract"
    assert informational.evidence[0]["source"] == "query_terms"
    assert abs(sum(informational.probabilities.values()) - 1) < 0.001

    branded = classify_query("SEO Monitor login", ["SEO Monitor"])
    assert branded.search_intent == "navigational"
    assert any(item["source"] == "branded_term" for item in branded.evidence)

    uncertain = classify_query("warmtepomp")
    assert uncertain.search_intent == "uncertain"
    assert uncertain.probabilities == {"uncertain": 1.0}


def test_page_rules_combine_prominent_content_and_query_weights() -> None:
    snapshot = UrlSnapshot(
        requested_url="https://example.com/offerte",
        title="Vraag een offerte aan",
        headings={"h1": ["Warmtepomp offerte"]},
        meta_description="Vergelijk de mogelijkheden.",
        main_content="Bekijk de prijs en bestel niet voordat u advies heeft ontvangen.",
    )
    result = classify_page(snapshot, {"transactional": 100, "commercial": 10})
    assert result.search_intent == "transactional"
    assert result.content_role == "convert"
    assert {item["source"] for item in result.evidence} == {"page_content", "gsc_queries"}


def test_analysis_caches_queries_and_is_idempotent() -> None:
    with SessionLocal() as db:
        client = Client(name="Intent customer")
        website = Website(
            client=client,
            name="Intent site",
            base_url="https://example.com",
            language="nl",
            country="NL",
        )
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        url = Url(
            website_id=website.id,
            normalized_url="https://example.com/offerte",
            current_status_code=200,
            is_indexable=True,
        )
        job = CrawlJob(website_id=website.id, job_type="full_site_crawl", status="succeeded")
        db.add_all([url, job])
        db.flush()
        run = CrawlRun(crawl_job_id=job.id, website_id=website.id, crawl_type="full_site_crawl")
        db.add(run)
        db.flush()
        snapshot = UrlSnapshot(
            url_id=url.id,
            crawl_run_id=run.id,
            checked_at=datetime.now(UTC),
            requested_url=url.normalized_url,
            status_code=200,
            content_type="text/html; charset=utf-8",
            title="Warmtepomp offerte",
            headings={"h1": ["Vraag een offerte aan"]},
            main_content="Bekijk onze prijzen en vraag direct een offerte aan.",
            main_content_hash="a" * 64,
            metadata_hash="b" * 64,
            is_indexable=True,
        )
        metric = SearchConsoleQueryMetric(
            website_id=website.id,
            url_id=url.id,
            date=date(2026, 8, 1),
            query="warmtepomp offerte",
            page_url=url.normalized_url,
            clicks=10,
            impressions=100,
            ctr=0.1,
            position=4,
        )
        db.add_all([snapshot, metric])
        db.commit()

        first = analyze_website_content(db, website.id, date(2026, 8, 1), date(2026, 8, 7))
        second = analyze_website_content(db, website.id, date(2026, 8, 1), date(2026, 8, 7))

        assert first == {"queries_classified": 1, "pages_created": 1, "pages_unchanged": 0}
        assert second == {"queries_classified": 0, "pages_created": 0, "pages_unchanged": 1}
        assert db.scalar(select(func.count()).select_from(QueryContentClassification)) == 1
        stored = db.scalar(select(UrlContentClassification))
        assert stored is not None
        assert stored.classification_version == CLASSIFICATION_VERSION
        assert stored.search_intent == "transactional"
        assert stored.source_coverage == {"crawl": True, "gsc_queries": True}

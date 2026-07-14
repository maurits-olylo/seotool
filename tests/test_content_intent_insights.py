from datetime import date

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.integrations import SearchConsoleQueryMetric
from app.models.website import Website
from app.services.content_intent_insights import build_content_intent_insights


def _website_with_snapshot(db, *, content: str, headings: dict[str, list[str]]):  # type: ignore[no-untyped-def]
    client = Client(name="Content intent client")
    website = Website(
        client=client,
        name="Kozijnbedrijf",
        base_url="https://example.com/",
    )
    db.add(website)
    db.flush()
    url = Url(
        website_id=website.id,
        normalized_url="https://example.com/kunststof-kozijnen",
        current_status_code=200,
        is_active=True,
        is_indexable=True,
    )
    db.add(url)
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
    db.add(
        UrlSnapshot(
            url_id=url.id,
            crawl_run_id=run.id,
            requested_url=url.normalized_url,
            final_url=url.normalized_url,
            status_code=200,
            content_type="text/html",
            title="Kunststof kozijnen",
            headings=headings,
            main_content=content,
            word_count=120,
            is_indexable=True,
        )
    )
    return website, url


def _query_metric(website, url):  # type: ignore[no-untyped-def]
    return SearchConsoleQueryMetric(
        website_id=website.id,
        url_id=url.id,
        date=date(2026, 6, 15),
        query="wat kosten kunststof kozijnen",
        page_url=url.normalized_url,
        clicks=8,
        impressions=500,
        ctr=0.016,
        position=9,
    )


def test_detects_material_question_without_price_answer() -> None:
    with SessionLocal() as db:
        website, url = _website_with_snapshot(
            db,
            content=("Wij leveren duurzame kunststof kozijnen met isolerend glas. " * 12),
            headings={"h1": ["Kunststof kozijnen"]},
        )
        db.add(_query_metric(website, url))
        db.commit()

        insights = build_content_intent_insights(
            db,
            website.id,
            date(2026, 6, 1),
            date(2026, 6, 30),
        )

    assert len(insights) == 1
    assert insights[0]["intent"] == "prijs"
    assert insights[0]["confidence"] == "hoog"
    assert insights[0]["impressions"] == 500


def test_ignores_question_that_is_clearly_answered() -> None:
    with SessionLocal() as db:
        website, url = _website_with_snapshot(
            db,
            content=(
                "Wat kosten kunststof kozijnen? De prijs hangt af van formaat en glas. "
                "Vraag een offerte aan voor een exacte berekening. " * 8
            ),
            headings={"h1": ["Kunststof kozijnen"], "h2": ["Wat kosten kozijnen?"]},
        )
        db.add(_query_metric(website, url))
        db.commit()

        insights = build_content_intent_insights(
            db,
            website.id,
            date(2026, 6, 1),
            date(2026, 6, 30),
        )

    assert insights == []

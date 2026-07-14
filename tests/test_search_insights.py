from datetime import date

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.integrations import SearchConsoleQueryMetric
from app.models.website import Website
from app.services.search_insights import build_search_insights


def _metric(
    website_id,
    metric_date: date,
    query: str,
    page_url: str,
    clicks: float,
    impressions: int,
    position: float,
) -> SearchConsoleQueryMetric:
    return SearchConsoleQueryMetric(
        website_id=website_id,
        date=metric_date,
        query=query,
        page_url=page_url,
        clicks=clicks,
        impressions=impressions,
        ctr=clicks / impressions if impressions else 0,
        position=position,
    )


def test_search_insights_identify_ctr_cannibalization_and_decline() -> None:
    with SessionLocal() as db:
        customer = Client(name="Search insights")
        db.add(customer)
        db.flush()
        website = Website(
            client_id=customer.id,
            name="Example",
            base_url="https://example.com",
        )
        db.add(website)
        db.flush()
        previous_date = date(2026, 1, 10)
        current_date = date(2026, 2, 10)
        db.add_all(
            [
                _metric(
                    website.id,
                    current_date,
                    "kunststof kozijnen",
                    "https://example.com/kozijnen",
                    10,
                    80,
                    5,
                ),
                _metric(
                    website.id,
                    current_date,
                    "kunststof kozijnen",
                    "https://example.com/kunststof",
                    8,
                    70,
                    6,
                ),
                _metric(
                    website.id,
                    current_date,
                    "kozijnen kopen",
                    "https://example.com/kozijnen",
                    5,
                    500,
                    7,
                ),
                _metric(
                    website.id,
                    previous_date,
                    "schuifpui",
                    "https://example.com/schuifpui",
                    40,
                    300,
                    5,
                ),
                _metric(
                    website.id,
                    current_date,
                    "schuifpui",
                    "https://example.com/schuifpui",
                    5,
                    200,
                    8,
                ),
            ]
        )
        db.commit()

        insights = build_search_insights(
            db,
            website.id,
            date(2026, 2, 1),
            date(2026, 2, 28),
            date(2026, 1, 1),
            date(2026, 1, 31),
        )

    assert {item["type"] for item in insights} == {
        "cannibalization",
        "ctr_opportunity",
        "declining_query",
    }


def test_search_insights_identify_dominant_ranking_url_change() -> None:
    with SessionLocal() as db:
        customer = Client(name="Ranking URL change")
        db.add(customer)
        db.flush()
        website = Website(
            client_id=customer.id,
            name="Example",
            base_url="https://example.com",
        )
        db.add(website)
        db.flush()
        db.add_all(
            [
                _metric(
                    website.id,
                    date(2026, 1, 10),
                    "kunststof kozijnen",
                    "https://example.com/oud",
                    30,
                    180,
                    4,
                ),
                _metric(
                    website.id,
                    date(2026, 1, 10),
                    "kunststof kozijnen",
                    "https://example.com/nieuw",
                    2,
                    20,
                    9,
                ),
                _metric(
                    website.id,
                    date(2026, 2, 10),
                    "kunststof kozijnen",
                    "https://example.com/oud",
                    3,
                    30,
                    8,
                ),
                _metric(
                    website.id,
                    date(2026, 2, 10),
                    "kunststof kozijnen",
                    "https://example.com/nieuw",
                    25,
                    170,
                    5,
                ),
            ]
        )
        db.commit()

        insights = build_search_insights(
            db,
            website.id,
            date(2026, 2, 1),
            date(2026, 2, 28),
            date(2026, 1, 1),
            date(2026, 1, 31),
        )

    switches = [item for item in insights if item["type"] == "ranking_url_changed"]
    assert len(switches) == 1
    assert switches[0]["previous_url"] == "https://example.com/oud"
    assert switches[0]["url"] == "https://example.com/nieuw"


def test_search_insights_ignore_minor_secondary_page_visibility() -> None:
    with SessionLocal() as db:
        customer = Client(name="Minor secondary page")
        db.add(customer)
        db.flush()
        website = Website(
            client_id=customer.id,
            name="Example",
            base_url="https://example.com",
        )
        db.add(website)
        db.flush()
        db.add_all(
            [
                _metric(
                    website.id,
                    date(2026, 2, 10),
                    "kozijnen",
                    "https://example.com/primair",
                    40,
                    900,
                    3,
                ),
                _metric(
                    website.id,
                    date(2026, 2, 10),
                    "kozijnen",
                    "https://example.com/secundair",
                    1,
                    20,
                    15,
                ),
            ]
        )
        db.commit()

        insights = build_search_insights(
            db,
            website.id,
            date(2026, 2, 1),
            date(2026, 2, 28),
            date(2026, 1, 1),
            date(2026, 1, 31),
        )

    assert not any(item["type"] == "cannibalization" for item in insights)

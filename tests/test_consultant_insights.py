from datetime import date

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.discovery import Url
from app.models.integrations import GoogleAnalyticsMetric, SearchConsoleMetric
from app.models.website import Website
from app.services.consultant_insights import build_consultant_insights


def test_consultant_insights_find_page_decline_and_conversion_gap() -> None:
    with SessionLocal() as db:
        customer = Client(name="Consultant insights")
        db.add(customer)
        db.flush()
        website = Website(
            client_id=customer.id,
            name="Example",
            base_url="https://example.com",
        )
        db.add(website)
        db.flush()
        page = Url(
            website_id=website.id,
            normalized_url="https://example.com/landing",
        )
        db.add(page)
        db.flush()
        db.add_all(
            [
                SearchConsoleMetric(
                    website_id=website.id,
                    url_id=page.id,
                    date=date(2026, 1, 10),
                    page_url=page.normalized_url,
                    clicks=50,
                    impressions=1_000,
                    ctr=0.05,
                    position=5,
                ),
                SearchConsoleMetric(
                    website_id=website.id,
                    url_id=page.id,
                    date=date(2026, 2, 10),
                    page_url=page.normalized_url,
                    clicks=10,
                    impressions=400,
                    ctr=0.025,
                    position=8,
                ),
                GoogleAnalyticsMetric(
                    website_id=website.id,
                    url_id=page.id,
                    date=date(2026, 2, 10),
                    landing_page="/landing",
                    sessions=250,
                    active_users=220,
                    key_events=0,
                ),
            ]
        )
        db.commit()

        insights = build_consultant_insights(
            db,
            website.id,
            date(2026, 2, 1),
            date(2026, 2, 28),
            date(2026, 1, 1),
            date(2026, 1, 31),
        )

    assert insights["search"][0]["type"] == "declining_page"
    assert insights["search"][0]["click_change_percent"] == -80.0
    assert insights["content"] == []
    assert insights["conversion"][0]["type"] == "conversion_opportunity"
    assert insights["conversion"][0]["url"] == "https://example.com/landing"


def test_consultant_insights_endpoint(client) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Insights API"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Insights site",
            "base_url": "https://insights.example.com",
        },
    ).json()

    response = client.get(f"/api/v1/websites/{website['id']}/consultant-insights?days=28")

    assert response.status_code == 200
    assert response.json()["days"] == 28
    assert response.json()["search"] == []
    assert response.json()["content"] == []
    assert response.json()["conversion"] == []

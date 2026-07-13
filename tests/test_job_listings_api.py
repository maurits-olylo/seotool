from datetime import date

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.models.discovery import Url
from app.models.issues import Issue
from app.models.jobs import JobListing


def test_job_listing_endpoint_returns_validation_issues(client: TestClient) -> None:
    customer = client.post("/api/v1/clients", json={"name": "Example"}).json()
    website = client.post(
        "/api/v1/websites",
        json={"client_id": customer["id"], "name": "Site", "base_url": "https://example.com"},
    ).json()
    with SessionLocal() as db:
        url = Url(
            website_id=website["id"],
            normalized_url="https://example.com/vacatures/seo-specialist",
            current_status_code=200,
            is_active=True,
            is_indexable=True,
        )
        db.add(url)
        db.flush()
        db.add(
            JobListing(
                website_id=website["id"],
                url_id=url.id,
                title="SEO specialist",
                valid_through=date(2026, 12, 31),
                detection_sources=["url_pattern", "page_text"],
                lifecycle_status="active",
                current_status_code=200,
                is_indexable=True,
                inbound_internal_links=4,
            )
        )
        db.add(
            Issue(
                website_id=website["id"],
                url_id=url.id,
                issue_type="job_posting_schema_missing",
                category="structured_data",
                severity="high",
                status="new",
                title="Vacature mist JobPosting-schema",
                description="Schema ontbreekt.",
                recommended_action="Voeg schema toe.",
            )
        )
        db.commit()

    response = client.get(f"/api/v1/websites/{website['id']}/job-listings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "total": 1,
        "active": 1,
        "expiring_soon": 0,
        "expired": 0,
        "removed": 0,
        "needs_attention": 1,
        "technical_errors": 1,
        "missing_schema": 1,
        "new_issues": 1,
    }
    assert payload["job_listings"][0]["validation_status"] == "error"
    assert payload["job_listings"][0]["issues"][0]["title"] == "Vacature mist JobPosting-schema"

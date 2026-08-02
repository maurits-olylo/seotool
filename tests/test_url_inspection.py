from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.discovery import Url
from app.models.integrations import UrlInspectionResult
from app.models.issues import Issue
from app.models.website import Website, WebsiteSettings
from app.services.url_inspection import (
    inspection_result_from_response,
    select_inspection_urls,
)


def test_parses_google_url_inspection_response() -> None:
    result = inspection_result_from_response(
        website_id=uuid4(),
        url_id=uuid4(),
        payload={
            "inspectionResult": {
                "inspectionResultLink": "https://search.google.com/example",
                "indexStatusResult": {
                    "verdict": "PASS",
                    "coverageState": "Submitted and indexed",
                    "robotsTxtState": "ALLOWED",
                    "indexingState": "INDEXING_ALLOWED",
                    "pageFetchState": "SUCCESSFUL",
                    "lastCrawlTime": "2026-07-30T12:00:00Z",
                    "googleCanonical": "https://example.com/google",
                    "userCanonical": "https://example.com/declared",
                    "referringUrls": ["https://example.com/source"],
                    "sitemap": ["https://example.com/sitemap.xml"],
                },
                "richResultsResult": {"verdict": "PASS", "detectedItems": []},
            }
        },
    )

    assert result.verdict == "PASS"
    assert result.last_crawl_time == datetime(2026, 7, 30, 12, tzinfo=UTC)
    assert result.google_canonical == "https://example.com/google"
    assert result.sitemap_urls == ["https://example.com/sitemap.xml"]
    assert result.rich_results["verdict"] == "PASS"


def test_selection_prioritizes_important_and_suspicious_stale_urls() -> None:
    with SessionLocal() as db:
        client = Client(name="Inspection client")
        website = Website(client=client, name="Inspection site", base_url="https://example.com/")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        regular = _url(db, website.id, "/regular")
        suspicious = _url(db, website.id, "/suspicious")
        important = _url(db, website.id, "/important", important=True)
        db.add(
            Issue(
                website_id=website.id,
                url_id=suspicious.id,
                issue_type="unexpected_noindex",
                category="indexation",
                severity="high",
                status="new",
                title="Indexation issue",
                description="Evidence",
                recommended_action="Review",
            )
        )
        db.add(
            UrlInspectionResult(
                website_id=website.id,
                url_id=regular.id,
                inspected_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        db.flush()

        selected = select_inspection_urls(db, website_id=website.id, limit=10)

        assert [url.id for url in selected] == [important.id, suspicious.id]
        assert regular.id not in {url.id for url in selected}


def test_inspection_results_preserve_history() -> None:
    with SessionLocal() as db:
        client = Client(name="History client")
        website = Website(client=client, name="History site", base_url="https://example.com/")
        website.settings = WebsiteSettings()
        db.add(website)
        db.flush()
        url = _url(db, website.id, "/page")
        db.add_all(
            [
                UrlInspectionResult(
                    website_id=website.id,
                    url_id=url.id,
                    inspected_at=datetime.now(UTC) - timedelta(days=10),
                    verdict="NEUTRAL",
                ),
                UrlInspectionResult(
                    website_id=website.id,
                    url_id=url.id,
                    inspected_at=datetime.now(UTC),
                    verdict="PASS",
                ),
            ]
        )
        db.commit()

        stored = list(
            db.scalars(
                select(UrlInspectionResult).where(UrlInspectionResult.url_id == url.id)
            )
        )
        assert {item.verdict for item in stored} == {"NEUTRAL", "PASS"}


def _url(db, website_id, path, *, important=False):  # type: ignore[no-untyped-def]
    url = Url(
        website_id=website_id,
        normalized_url=f"https://example.com{path}",
        current_status_code=200,
        is_active=True,
        is_indexable=True,
        is_important=important,
    )
    db.add(url)
    db.flush()
    return url

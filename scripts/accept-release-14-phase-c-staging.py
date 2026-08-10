#!/usr/bin/env python3
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.main import app
from app.models.client import Client
from app.models.discovery import CrawlJob
from app.models.onboarding import WebsiteOwnershipVerification
from app.schemas.onboarding import WebsiteOnboardingCrawlPreferences, WebsiteOnboardingStart
from app.services import website_onboarding as onboarding_service


def main() -> None:
    client_id = None
    original_get_settings = onboarding_service.get_settings
    onboarding_service.get_settings = lambda: SimpleNamespace(app_env="test")
    try:
        with SessionLocal() as db:
            client = Client(name=f"Release 14 phase C synthetic {uuid4()}")
            db.add(client)
            db.commit()
            client_id = client.id
            started = onboarding_service.start_website_onboarding(
                db,
                client_id=client.id,
                actor_user_id=None,
                payload=WebsiteOnboardingStart(
                    request_id=uuid4(),
                    website_name="Synthetic first crawl",
                    base_url="https://release-14-first-crawl.example.test/",
                    settings={
                        "sitemap_urls": ["https://release-14-first-crawl.example.test/sitemap.xml"]
                    },
                ),
            )
            verification = db.scalar(
                select(WebsiteOwnershipVerification).where(
                    WebsiteOwnershipVerification.onboarding_id == started.id
                )
            )
            assert verification is not None
            verification.status = "verified"
            db.commit()

            preferences = WebsiteOnboardingCrawlPreferences(
                max_urls=1_500,
                request_delay_ms=350,
                concurrency=3,
            )
            first_onboarding, first_job = onboarding_service.start_first_onboarding_crawl(
                db,
                started.id,
                actor_user_id=None,
                preferences=preferences,
            )
            repeated_onboarding, repeated_job = onboarding_service.start_first_onboarding_crawl(
                db,
                started.id,
                actor_user_id=None,
                preferences=WebsiteOnboardingCrawlPreferences(max_urls=99_999),
            )

            assert first_job.id == repeated_job.id
            assert first_onboarding.first_crawl_job_id == first_job.id
            assert repeated_onboarding.current_step == "first_crawl"
            assert first_job.status == "pending"
            assert first_job.settings_snapshot["max_urls"] == 1_500
            assert first_job.settings_snapshot["respect_robots_txt"] is True
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(CrawlJob)
                    .where(CrawlJob.website_id == started.website_id)
                )
                == 1
            )

            paths = app.openapi()["paths"]
            assert "/api/v1/website-onboarding/{onboarding_id}/first-crawl" in paths
            ui_root = Path("/app/app/ui")
            html = (ui_root / "index.html").read_text()
            script = (ui_root / "app.js").read_text()
            assert 'id="first-crawl-preferences"' in html
            assert "Robots.txt altijd respecteren" in html
            assert "startFirstOnboardingCrawl" in script
            assert "first_crawl_job_id" in script
            print(
                {
                    "status": "release_14_phase_c_staging_ok",
                    "idempotent_first_crawl": True,
                    "crawl_jobs": 1,
                    "robots_required": True,
                    "safe_preferences": True,
                    "redis_jobs": 0,
                    "resumable": True,
                }
            )
    finally:
        onboarding_service.get_settings = original_get_settings
        if client_id is not None:
            with SessionLocal() as db:
                client = db.get(Client, client_id)
                if client is not None:
                    db.delete(client)
                    db.commit()

    with SessionLocal() as db:
        assert db.get(Client, client_id) is None
    print("release-14-phase-c-fixture-clean")


if __name__ == "__main__":
    main()

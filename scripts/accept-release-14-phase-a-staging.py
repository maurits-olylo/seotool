#!/usr/bin/env python3
from uuid import uuid4

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.main import app
from app.models.client import Client
from app.models.discovery import CrawlJob
from app.models.onboarding import WebsiteOnboarding, WebsiteOwnershipVerification
from app.models.website import Website
from app.schemas.onboarding import WebsiteOnboardingStart
from app.services.website_onboarding import start_website_onboarding


def main() -> None:
    client_id = None
    try:
        with SessionLocal() as db:
            client = Client(name=f"Release 14 phase A synthetic {uuid4()}")
            db.add(client)
            db.commit()
            client_id = client.id
            request_id = uuid4()
            payload = WebsiteOnboardingStart(
                request_id=request_id,
                website_name="Synthetic fresh website",
                base_url="https://release-14-onboarding.example.test/",
            )
            first = start_website_onboarding(
                db, client_id=client.id, actor_user_id=None, payload=payload
            )
            repeated = start_website_onboarding(
                db, client_id=client.id, actor_user_id=None, payload=payload
            )
            verification = db.scalar(
                select(WebsiteOwnershipVerification).where(
                    WebsiteOwnershipVerification.onboarding_id == first.id
                )
            )
            assert verification is not None
            assert first.id == repeated.id
            assert first.verification_file_content is not None
            assert repeated.verification_file_content is None
            token = first.verification_file_content.split("=", 1)[1]
            assert token not in verification.token_hash
            assert db.scalar(select(func.count()).select_from(Website)) >= 1
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(WebsiteOnboarding)
                    .where(WebsiteOnboarding.client_id == client.id)
                )
                == 1
            )
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(CrawlJob)
                    .where(CrawlJob.website_id == first.website_id)
                )
                == 0
            )
            paths = app.openapi()["paths"]
            assert "/api/v1/website-onboarding/clients/{client_id}" in paths
            assert "/api/v1/website-onboarding/{onboarding_id}" in paths
            assert "/api/v1/website-onboarding/{onboarding_id}/verification/check" in paths
            print(
                {
                    "status": "release_14_phase_a_staging_ok",
                    "idempotent": True,
                    "token_hashed": True,
                    "crawl_jobs": 0,
                    "routes": 3,
                }
            )
    finally:
        if client_id is not None:
            with SessionLocal() as db:
                client = db.get(Client, client_id)
                if client is not None:
                    db.delete(client)
                    db.commit()

    with SessionLocal() as db:
        assert db.get(Client, client_id) is None
    print("release-14-phase-a-fixture-clean")


if __name__ == "__main__":
    main()

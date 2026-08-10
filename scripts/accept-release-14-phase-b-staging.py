#!/usr/bin/env python3
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.main import app
from app.models.client import Client
from app.models.discovery import CrawlJob
from app.models.onboarding import WebsiteOwnershipVerification
from app.models.user import SecurityAuditEvent
from app.schemas.onboarding import WebsiteOnboardingStart
from app.services.website_onboarding import (
    renew_website_verification_file,
    start_website_onboarding,
    token_hash,
)


def main() -> None:
    client_id = None
    try:
        with SessionLocal() as db:
            client = Client(name=f"Release 14 phase B synthetic {uuid4()}")
            db.add(client)
            db.commit()
            client_id = client.id
            started = start_website_onboarding(
                db,
                client_id=client.id,
                actor_user_id=None,
                payload=WebsiteOnboardingStart(
                    request_id=uuid4(),
                    website_name="Synthetic guided verification",
                    base_url="https://release-14-verification.example.test/",
                ),
            )
            verification = db.scalar(
                select(WebsiteOwnershipVerification).where(
                    WebsiteOwnershipVerification.onboarding_id == started.id
                )
            )
            assert verification is not None
            previous_hash = verification.token_hash
            verification.attempt_count = 3
            db.commit()

            file_content = renew_website_verification_file(
                db,
                started.id,
                actor_user_id=None,
            )
            db.refresh(verification)
            token = file_content.removeprefix("thactual-site-verification=")
            assert token_hash(token) == verification.token_hash
            assert verification.token_hash != previous_hash
            assert token not in verification.token_hash
            assert verification.attempt_count == 0
            assert verification.status == "pending"
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(CrawlJob)
                    .where(CrawlJob.website_id == started.website_id)
                )
                == 0
            )
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(SecurityAuditEvent)
                    .where(
                        SecurityAuditEvent.event_type
                        == "website_onboarding.verification_file_renewed",
                        SecurityAuditEvent.client_id == client.id,
                    )
                )
                == 1
            )

            paths = app.openapi()["paths"]
            assert "/api/v1/website-onboarding/{onboarding_id}/verification/file" in paths
            ui_root = Path("/app/app/ui")
            html = (ui_root / "index.html").read_text()
            script = (ui_root / "app.js").read_text()
            assert 'id="website-verification-step"' in html
            assert 'id="download-verification-file"' in html
            assert "resumeWebsiteOnboarding" in script
            assert 'credentials: "same-origin"' in script
            print(
                {
                    "status": "release_14_phase_b_staging_ok",
                    "token_rotated": True,
                    "token_hashed": True,
                    "crawl_jobs": 0,
                    "guided_ui": True,
                    "resume_after_refresh": True,
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
    print("release-14-phase-b-fixture-clean")


if __name__ == "__main__":
    main()

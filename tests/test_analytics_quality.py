from datetime import date

from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.discovery import Url
from app.models.integrations import (
    GoogleAnalyticsLandingPageEventMetric,
    GoogleAnalyticsMetric,
    IntegrationConnection,
    WebsiteIntegration,
)
from app.models.issues import ActivityLog, Issue
from app.models.website import Website, WebsiteSettings
from app.services.analytics_quality import reconcile_ga4_quality_issues


def test_ga4_quality_issue_is_deduplicated_resolved_verified_and_reopened() -> None:
    checked_date = date(2026, 8, 1)
    with SessionLocal() as db:
        customer = Client(name="Analytics quality client")
        website = Website(
            client=customer,
            name="Analytics quality site",
            base_url="https://quality.example.com",
        )
        website.settings = WebsiteSettings(primary_analytics_source="ga4")
        db.add(website)
        db.flush()
        connection = IntegrationConnection(
            client_id=customer.id,
            provider="google",
            status="connected",
        )
        db.add(connection)
        db.flush()
        page = Url(
            website_id=website.id,
            normalized_url="https://quality.example.com/bedankt",
        )
        db.add_all(
            [
                page,
                WebsiteIntegration(
                    website_id=website.id,
                    connection_id=connection.id,
                    service="ga4",
                    external_property_id="properties/quality",
                    status="active",
                    settings={"qualified_key_events": ["lead"]},
                ),
            ]
        )
        db.flush()
        db.add_all(
            [
                GoogleAnalyticsMetric(
                    website_id=website.id,
                    url_id=page.id,
                    date=checked_date,
                    landing_page="/bedankt",
                    sessions=2,
                    active_users=2,
                    key_events=999,
                ),
                GoogleAnalyticsLandingPageEventMetric(
                    website_id=website.id,
                    url_id=page.id,
                    date=checked_date,
                    landing_page="/bedankt",
                    event_name="lead",
                    key_events=20,
                ),
            ]
        )
        db.flush()

        first = reconcile_ga4_quality_issues(db, website.id, checked_date, checked_date)
        second = reconcile_ga4_quality_issues(db, website.id, checked_date, checked_date)
        assert first == {"anomalies": 1, "created": 1, "resolved": 0, "verified": 0}
        assert second == {"anomalies": 1, "created": 0, "resolved": 0, "verified": 0}
        assert len(list(db.scalars(select(Issue)))) == 1

        db.execute(delete(GoogleAnalyticsLandingPageEventMetric))
        clean = reconcile_ga4_quality_issues(db, website.id, checked_date, checked_date)
        verified = reconcile_ga4_quality_issues(db, website.id, checked_date, checked_date)
        issue = db.scalar(select(Issue))
        assert clean["resolved"] == 1
        assert verified["verified"] == 1
        assert issue is not None and issue.status == "verified"

        db.add(
            GoogleAnalyticsLandingPageEventMetric(
                website_id=website.id,
                url_id=page.id,
                date=checked_date,
                landing_page="/bedankt",
                event_name="lead",
                key_events=20,
            )
        )
        db.flush()
        reopened = reconcile_ga4_quality_issues(db, website.id, checked_date, checked_date)
        assert reopened["anomalies"] == 1
        assert issue.status == "new"
        assert len(list(db.scalars(select(Issue)))) == 1

        checks = list(
            db.scalars(
                select(ActivityLog).where(ActivityLog.activity_type == "analytics_quality_checked")
            )
        )
        assert [item.details["outcome"] for item in checks] == [
            "attention_needed",
            "attention_needed",
            "resolved",
            "verified",
            "attention_needed",
        ]
        assert checks[0].details["anomalies"][0]["events"] == 20
        assert checks[0].details["anomalies"][0]["sessions"] == 2

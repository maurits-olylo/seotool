from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.common import utc_now
from app.models.discovery import Url, UrlSource
from app.models.issues import Issue
from app.services.issue_engine import reconcile_issues
from app.services.technical_checks import IssueSignal


def detect_orphan_pages(db: Session, *, website_id: object, crawl_run_id: object) -> list[Url]:
    orphan_urls = list(
        db.scalars(
            select(Url)
            .join(UrlSource, UrlSource.url_id == Url.id)
            .where(
                Url.website_id == website_id,
                Url.is_active.is_(True),
                Url.crawl_depth.is_(None),
                UrlSource.source_type == "sitemap",
            )
            .distinct()
            .order_by(Url.normalized_url)
        )
    )
    for url in orphan_urls:
        reconcile_issues(
            db,
            website_id=website_id,
            url_id=url.id,
            crawl_run_id=crawl_run_id,
            snapshot_id=None,
            signals=[
                IssueSignal(
                    issue_type="orphan_page",
                    category="internal_links",
                    severity="medium",
                    title="Orphan page",
                    description=(
                        "De URL staat in een sitemap maar is niet bereikbaar via interne links."
                    ),
                    recommended_action=(
                        "Voeg een relevante interne link toe of verwijder de URL uit de sitemap."
                    ),
                    evidence={"url": url.normalized_url, "crawl_depth": None},
                )
            ],
            checked_issue_types={"orphan_page"},
        )
    orphan_ids = {url.id for url in orphan_urls}
    existing = list(
        db.scalars(
            select(Issue).where(
                Issue.website_id == website_id,
                Issue.issue_type == "orphan_page",
                Issue.status.not_in(["resolved", "verified", "ignored", "accepted_risk"]),
            )
        )
    )
    for issue in existing:
        if issue.url_id not in orphan_ids:
            issue.status = "resolved"
            issue.resolved_at = utc_now()
    return orphan_urls

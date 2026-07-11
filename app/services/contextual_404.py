from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.crawl import UrlLink
from app.models.discovery import Url, UrlSource
from app.services.issue_engine import reconcile_issues
from app.services.technical_checks import IssueSignal

CONTEXTUAL_404_TYPES = {"http_404", "internally_linked_404", "sitemap_404"}


def classify_404_issues(
    db: Session, *, website_id: object, crawl_run_id: object
) -> None:
    urls = list(
        db.scalars(
            select(Url).where(
                Url.website_id == website_id,
                Url.is_active.is_(True),
                Url.current_status_code == 404,
            )
        )
    )
    for url in urls:
        incoming_links = db.scalar(
            select(func.count(UrlLink.id)).where(
                UrlLink.crawl_run_id == crawl_run_id,
                UrlLink.target_url_id == url.id,
                UrlLink.is_internal.is_(True),
            )
        ) or 0
        in_sitemap = db.scalar(
            select(UrlSource.id).where(
                UrlSource.url_id == url.id,
                UrlSource.source_type == "sitemap",
            )
        )
        signal = _signal(incoming_links=incoming_links, in_sitemap=in_sitemap is not None)
        reconcile_issues(
            db,
            website_id=website_id,
            url_id=url.id,
            crawl_run_id=crawl_run_id,
            snapshot_id=None,
            signals=[signal],
            checked_issue_types=CONTEXTUAL_404_TYPES,
        )
    db.commit()


def _signal(*, incoming_links: int, in_sitemap: bool) -> IssueSignal:
    if incoming_links:
        return IssueSignal(
            issue_type="internally_linked_404",
            category="internal_links",
            severity="high",
            title="Interne links wijzen naar een 404",
            description=f"De 404-URL ontvangt {incoming_links} interne links.",
            recommended_action="Herstel de interne links of stel een relevante redirect in.",
            evidence={"incoming_internal_links": incoming_links},
        )
    if in_sitemap:
        return IssueSignal(
            issue_type="sitemap_404",
            category="indexation",
            severity="medium",
            title="404-URL staat in de sitemap",
            description="De URL staat in de XML-sitemap maar geeft een 404.",
            recommended_action="Verwijder de URL uit de sitemap of herstel de pagina.",
            evidence={"in_sitemap": True},
        )
    return IssueSignal(
        issue_type="http_404",
        category="reachability",
        severity="high",
        title="Pagina geeft 404",
        description="De bekende URL geeft een 404.",
        recommended_action="Herstel de pagina of stel een relevante redirect in.",
        evidence={"status_code": 404},
    )

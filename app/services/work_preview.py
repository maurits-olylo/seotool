"""Read-only pilot: explain readiness without creating or resolving work."""

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.common import utc_now
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import Url
from app.models.issues import Issue, IssueOccurrence
from app.models.recommendations import RecommendationTask, RecommendationTaskIssue
from app.services.recommendation_library import recommendation_for_issue_type

LANES = {
    "execute": "Nu uitvoeren",
    "decision": "Beslissing nodig",
    "research": "Eerst onderzoeken",
    "periodic": "Periodieke beoordeling",
    "history": "Resultaten en historie",
    "unassessed": "Nog niet beoordeeld",
}
DECISIONS = {
    "http_404",
    "http_410",
    "sitemap_404",
    "expired_job_posting",
    "expired_job_posting_linked",
    "expired_job_posting_404",
    "duplicate_meta_description",
    "duplicate_title",
    "duplicate_content",
}
RESEARCH = {
    "orphan_page",
    "structured_data_visible_content_mismatch",
    "internally_linked_404",
    "multiple_broken_internal_links",
    "internally_linked_redirect",
    "multiple_redirected_internal_links",
    "cms_link_placeholder",
    "http_5xx",
    "missing_meta_description",
}
HISTORY = {"verified", "ignored", "accepted_risk"}
ROLES = {
    "content": "Redactie / inhoudelijk verantwoordelijke",
    "development": "Webbouwer",
    "seo_analytics": "SEO-manager",
    "project_management": "Opdrachtgever",
}


def assess(
    issue: Issue,
    *,
    current_evidence: bool,
    partial: bool,
    tasks: list[RecommendationTask],
    now: datetime,
) -> dict[str, Any]:
    """A template's 'direct' label is not approval or proof of a chosen solution."""
    definition = recommendation_for_issue_type(issue.issue_type)
    role = ROLES.get(definition.primary_role, "SEO-manager") if definition else "SEO-manager"
    criteria = "Leg de beoordeling, gebruikte meting en gekozen vervolgstap vast."
    if issue.status in HISTORY:
        lane, reason = (
            "history",
            (
                "Signaal is geverifieerd verdwenen."
                if issue.status == "verified"
                else "Bewust afgehandeld; dit bewijst geen websiteherstel."
            ),
        )
        step = "Bekijk het vastgelegde resultaat; maak geen dubbele opdracht."
    elif issue.status == "resolved":
        lane, reason, step = (
            "research",
            "Herstel wacht nog op verificatie.",
            "Controleer het herstel met nieuw bewijs.",
        )
    elif (
        issue.issue_type == "possibly_outdated_content"
        and issue.severity != "high"
        and not (issue.due_date and issue.due_date <= now.date())
    ):
        lane, reason = "periodic", "Een oude datum bewijst geen inhoudelijke fout."
        step, role = (
            "Beoordeel archieffunctie, tijdgebonden uitspraken en bronnen.",
            "Eindredacteur",
        )
    elif issue.issue_type not in DECISIONS | RESEARCH | {"possibly_outdated_content"}:
        lane, reason, step = (
            "unassessed",
            "Dit type valt buiten de onderzochte pilotregels.",
            "Beoordeel bewijs en gewenste uitkomst voordat werk wordt vrijgegeven.",
        )
    elif not current_evidence or issue.confidence != "high" or issue.status == "review":
        lane, reason = "research", "Bewijs is niet actueel genoeg, onzeker of nog ter beoordeling."
        step = "Controleer de nieuwste meting en de onderbouwing van dit specifieke signaal."
    elif issue.issue_type in DECISIONS:
        lane, reason = "decision", "De juiste uitvoering hangt af van een inhoudelijk besluit."
        step = (
            definition.steps[0]
            if definition and definition.feasibility == "needs_decision"
            else (
                "Bepaal de gewenste functie van de pagina en of behouden, aanpassen "
                "of samenvoegen passend is."
            )
        )
        role = "Inhoudelijk verantwoordelijke / SEO-manager"
    else:
        lane, reason = (
            "research",
            "Een technisch signaal alleen legt de juiste oplossing nog niet vast.",
        )
        step = "Controleer bron, doel en bedoelde uitkomst; leg de concrete wijziging vast."
    # Existing work remains visible. Only already approved, direct work can qualify.
    approved = next(
        (
            task
            for task in tasks
            if task.status in {"planned", "in_progress"}
            and task.feasibility == "direct"
            and task.assigned_to_user_id
            and not task.dependencies
            and not task.required_input
            and definition
            and task.definition_version == definition.version
            and task.recommendation_type == definition.key
        ),
        None,
    )
    if (
        lane == "research"
        and current_evidence
        and not partial
        and approved
        and issue.status in {"accepted", "planned", "in_progress"}
        and issue.confidence == "high"
        and issue.issue_type in RESEARCH
        and approved.steps
        and approved.acceptance_criteria
    ):
        lane, reason = (
            "execute",
            "Er bestaat al toegewezen direct werk met stappen en gereedcriteria.",
        )
        step, criteria = approved.steps[0], " · ".join(approved.acceptance_criteria)
        role = ROLES.get(approved.primary_role, role)
    if partial:
        reason += " De broncrawl is deels geslaagd; ontbrekende routes zijn niet bewezen."
    if tasks:
        reason += " Er bestaat al werk: beoordeel dat voordat een nieuwe taak wordt gemaakt."
    return dict(
        lane=lane,
        reason=reason,
        first_step=step,
        role=role,
        completion=criteria,
        current_evidence=current_evidence,
    )


def preview(
    db: Session,
    website_id: UUID,
    *,
    lane: str | None = None,
    offset: int = 0,
    limit: int = 20,
    q: str = "",
) -> dict[str, Any]:
    now = utc_now()
    issues = list(db.scalars(select(Issue).where(Issue.website_id == website_id)))
    # Narrow projections: never load page HTML/content for the pilot.
    snapshots = (
        select(
            UrlSnapshot.id,
            UrlSnapshot.url_id,
            UrlSnapshot.checked_at,
            func.row_number()
            .over(
                partition_by=UrlSnapshot.url_id,
                order_by=(UrlSnapshot.checked_at.desc(), UrlSnapshot.id.desc()),
            )
            .label("n"),
        )
        .join(Url, Url.id == UrlSnapshot.url_id)
        .where(Url.website_id == website_id)
        .subquery()
    )
    latest = {row.url_id: row for row in db.execute(select(snapshots).where(snapshots.c.n == 1))}
    occurrences = (
        select(
            IssueOccurrence.issue_id,
            IssueOccurrence.snapshot_id,
            IssueOccurrence.crawl_run_id,
            IssueOccurrence.detected_at,
            func.row_number()
            .over(
                partition_by=IssueOccurrence.issue_id,
                order_by=(IssueOccurrence.detected_at.desc(), IssueOccurrence.id.desc()),
            )
            .label("n"),
        )
        .join(Issue, Issue.id == IssueOccurrence.issue_id)
        .where(Issue.website_id == website_id)
        .subquery()
    )
    evidence = {
        row.issue_id: row for row in db.execute(select(occurrences).where(occurrences.c.n == 1))
    }
    runs = dict(
        db.execute(
            select(CrawlRun.id, CrawlRun.status).where(CrawlRun.website_id == website_id)
        ).all()
    )
    urls = dict(
        db.execute(select(Url.id, Url.normalized_url).where(Url.website_id == website_id)).all()
    )
    tasks: dict[UUID, list[RecommendationTask]] = {}
    for issue_id, task in db.execute(
        select(RecommendationTaskIssue.issue_id, RecommendationTask)
        .join(RecommendationTask, RecommendationTask.id == RecommendationTaskIssue.task_id)
        .where(RecommendationTask.website_id == website_id)
    ):
        tasks.setdefault(issue_id, []).append(task)
    items = []
    for issue in issues:
        measured = latest.get(issue.url_id)
        occurrence = evidence.get(issue.id)
        fresh = bool(
            measured
            and occurrence
            and occurrence.snapshot_id == measured.id
            and measured.checked_at.replace(tzinfo=UTC) >= now - timedelta(days=7)
            and runs.get(occurrence.crawl_run_id) in {"succeeded", "partially_succeeded"}
        )
        linked = sorted(tasks.get(issue.id, []), key=lambda task: str(task.id))
        result = assess(
            issue,
            current_evidence=fresh,
            partial=bool(occurrence and runs.get(occurrence.crawl_run_id) == "partially_succeeded"),
            tasks=linked,
            now=now,
        )
        items.append(
            dict(
                issue_id=issue.id,
                title=issue.title,
                issue_type=issue.issue_type,
                url=urls.get(issue.url_id),
                severity=issue.severity,
                status=issue.status,
                description=issue.description,
                last_seen_at=issue.last_detected_at,
                evidence_at=occurrence.detected_at if occurrence else None,
                snapshot_id=occurrence.snapshot_id if occurrence else None,
                latest_checked_at=measured.checked_at if measured else None,
                tasks=[dict(id=t.id, title=t.title, status=t.status) for t in linked],
                **result,
            )
        )
    counts = Counter(item["lane"] for item in items)
    selected = [
        item
        for item in items
        if (not lane or item["lane"] == lane)
        and q.casefold() in (item["title"] + " " + (item["url"] or "")).casefold()
    ]
    selected.sort(
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}.get(item["severity"], 3),
            str(item["issue_id"]),
        )
    )
    return dict(
        generated_at=now,
        rule_version="pilot-1",
        total_signals=len(items),
        counts={key: counts[key] for key in LANES},
        total=len(selected),
        items=selected[offset : offset + limit],
        lanes=LANES,
    )

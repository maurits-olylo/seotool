"""Read-only pilot: explain readiness without creating or resolving work."""

import json
from collections import Counter
from collections.abc import Iterator
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Text, cast, func, select
from sqlalchemy.orm import Session

from app.models.common import utc_now
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import Url
from app.models.issues import Issue, IssueOccurrence
from app.models.recommendations import RecommendationTask, RecommendationTaskIssue
from app.services.recommendation_library import recommendation_for_issue_type
from app.services.work_preview_guidance import evidence_facts, evidence_state, next_step
from app.services.work_preview_opportunities import query_reviews

LANES = {
    "execute": "Nu uitvoeren",
    "decision": "Beslissing nodig",
    "research": "Eerst onderzoeken",
    "periodic": "Periodieke beoordeling",
    "verification": "Herstel controleren",
    "opportunity": "Inhoudelijke kansen",
    "history": "Resultaten en historie",
    "unassessed": "Nog niet beoordeeld",
}


def task_readiness(db: Session, task: RecommendationTask, issue_ids: list[UUID]) -> dict:
    """Use the same evidence rules for this task, including every linked issue."""
    ids = list(set(issue_ids + ([task.primary_issue_id] if task.primary_issue_id else [])))
    data = preview(
        db,
        task.website_id,
        issue_ids=ids,
        task_id=task.id,
        include_history=True,
        limit=max(1, len(ids)),
    )
    items = data["items"]
    blocked = next((item for item in items if item["lane"] != "execute"), None)
    if not items or blocked:
        return {
            "lane": blocked["lane"] if blocked else "unassessed",
            "label": LANES[blocked["lane"]] if blocked else "Eerst beoordelen",
            "reason": blocked["reason"] if blocked else "Onderbouwend signaal ontbreekt.",
            "first_step": blocked["first_step"]
            if blocked
            else "Controleer bewijs en gewenste uitkomst.",
        }
    return {
        "lane": "execute",
        "label": LANES["execute"],
        "reason": items[0]["reason"],
        "first_step": items[0]["first_step"],
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
    evidence_reason: str = "De passende bewijsmeting ontbreekt.",
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
            "verification",
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
        lane = "research"
        reasons = []
        if not current_evidence:
            reasons.append(evidence_reason)
        if issue.confidence != "high":
            reasons.append("De detectie is onzeker; een inhoudelijke beoordeling ontbreekt.")
        if issue.status == "review":
            reasons.append("Dit signaal staat expliciet ter beoordeling.")
        reason = " ".join(reasons)
        step = (
            definition.steps[0]
            if definition and definition.steps
            else "Controleer de vacaturestatus en sluitingsdatum."
        )
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
    if lane in {"research", "decision"} and not issue.issue_type.startswith("expired_job_posting"):
        step, role, criteria = next_step(issue.issue_type)
    if lane == "verification":
        _, role, _ = next_step(issue.issue_type)
        step = (
            "Controleer of een route vanaf de homepage in een volledige "
            "siteanalyse aantoonbaar is; een light check is hiervoor onvoldoende."
            if issue.issue_type == "orphan_page"
            else (
                "Vergelijk de meting na het gemelde herstel met het oorspronkelijke "
                "bewijs. Controleer hetzelfde onderdeel voordat het signaal wordt geverifieerd."
            )
        )
        criteria = (
            "De passende nameting bevestigt het herstel, of laat concreet zien "
            "wat nog niet is opgelost."
        )
    if lane == "history":
        criteria = "Geen nieuwe opdracht nodig voor dit afgehandelde signaal."
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
    if partial and issue.issue_type == "orphan_page" and lane != "history":
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


def read_evidence(db: Session, occurrence_ids: list[UUID]) -> Iterator[tuple[UUID, dict]]:
    """Decode raw PostgreSQL JSON in Python, including escaped control characters."""
    if not occurrence_ids:
        return
    for occurrence_id, raw in db.execute(
        select(IssueOccurrence.id, cast(IssueOccurrence.evidence, Text))
        .where(IssueOccurrence.id.in_(occurrence_ids))
        .execution_options(yield_per=200)
    ):
        payload = json.loads(raw) if raw else {}
        yield occurrence_id, payload if isinstance(payload, dict) else {}


def preview(
    db: Session,
    website_id: UUID,
    *,
    lane: str | None = None,
    offset: int = 0,
    limit: int = 20,
    q: str = "",
    include_history: bool = False,
    issue_ids: list[UUID] | None = None,
    task_id: UUID | None = None,
) -> dict[str, Any]:
    now = utc_now()
    issue_query = select(Issue).where(Issue.website_id == website_id)
    if issue_ids is not None:
        issue_query = issue_query.where(Issue.id.in_(issue_ids))
    issues = list(db.scalars(issue_query))
    scoped_urls = [i.url_id for i in issues if i.url_id]

    # Narrow projections: never load page HTML/content for the pilot.
    snapshots = (
        select(
            UrlSnapshot.id,
            UrlSnapshot.url_id,
            UrlSnapshot.checked_at,
            UrlSnapshot.status_code,
            UrlSnapshot.final_url,
            UrlSnapshot.error_message,
            func.row_number()
            .over(
                partition_by=UrlSnapshot.url_id,
                order_by=(UrlSnapshot.checked_at.desc(), UrlSnapshot.id.desc()),
            )
            .label("n"),
        )
        .join(Url, Url.id == UrlSnapshot.url_id)
        .where(Url.website_id == website_id)
        .where(Url.id.in_(scoped_urls) if issue_ids is not None else True)
        .subquery()
    )
    latest = {row.url_id: row for row in db.execute(select(snapshots).where(snapshots.c.n == 1))}
    analysis_query = (
        select(
            UrlSnapshot.id,
            UrlSnapshot.url_id,
            UrlSnapshot.checked_at,
            UrlSnapshot.status_code,
            UrlSnapshot.final_url,
            UrlSnapshot.error_message,
            func.row_number()
            .over(
                partition_by=UrlSnapshot.url_id,
                order_by=(UrlSnapshot.checked_at.desc(), UrlSnapshot.id.desc()),
            )
            .label("n"),
        )
        .join(Url, Url.id == UrlSnapshot.url_id)
        .where(Url.website_id == website_id, UrlSnapshot.metadata_hash.is_not(None))
        .where(Url.id.in_(scoped_urls) if issue_ids is not None else True)
        .subquery()
    )
    analyzed = {
        row.url_id: row for row in db.execute(select(analysis_query).where(analysis_query.c.n == 1))
    }
    occurrences = (
        select(
            IssueOccurrence.id,
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
        .where(Issue.id.in_(issue_ids) if issue_ids is not None else True)
        .subquery()
    )
    evidence = {
        row.issue_id: row for row in db.execute(select(occurrences).where(occurrences.c.n == 1))
    }
    # PostgreSQL json can store escaped NUL, but ->> parses and rejects it even
    # in unrelated fields. Read only required latest evidence as raw text and
    # decode in Python; never rewrite historical evidence to make a read succeed.
    flag_ids = [
        evidence[issue.id].id
        for issue in issues
        if issue.id in evidence
        and issue.issue_type in {"orphan_page", "structured_data_visible_content_mismatch"}
    ]
    flags = {}
    for occurrence_id, payload in read_evidence(db, flag_ids):
        flags[occurrence_id] = {
            "root_route_checked": isinstance(payload, dict)
            and payload.get("root_route_checked") is True,
            "comparison_version": payload.get("comparison_version")
            if isinstance(payload, dict) and type(payload.get("comparison_version")) is int
            else None,
        }
    runs = {
        run.id: run for run in db.scalars(select(CrawlRun).where(CrawlRun.website_id == website_id))
    }
    full_runs = [
        r
        for r in runs.values()
        if r.crawl_type == "full_site_crawl" and r.status in {"succeeded", "partially_succeeded"}
    ]
    latest_full = max(full_runs, key=lambda r: r.started_at) if full_runs else None
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
        fresh, evidence_code, evidence_reason = evidence_state(
            issue.issue_type,
            occurrence,
            measured,
            analyzed.get(issue.url_id),
            runs,
            latest_full,
            now,
            flags=flags.get(occurrence.id) if occurrence else None,
        )
        linked = sorted(tasks.get(issue.id, []), key=lambda task: str(task.id))
        result = assess(
            issue,
            current_evidence=fresh,
            partial=bool(
                occurrence
                and runs.get(occurrence.crawl_run_id)
                and runs[occurrence.crawl_run_id].status == "partially_succeeded"
            ),
            tasks=[t for t in linked if task_id is None or t.id == task_id],
            now=now,
            evidence_reason=evidence_reason,
        )
        items.append(
            dict(
                issue_id=issue.id,
                url_id=issue.url_id,
                source_run_id=latest_full.id if latest_full and latest_full.finished_at else None,
                source_run_at=latest_full.finished_at if latest_full else None,
                source_run_status=latest_full.status if latest_full else None,
                evidence_code=evidence_code,
                evidence_reason=evidence_reason,
                analysis_checked_at=analyzed[issue.url_id].checked_at
                if issue.url_id in analyzed
                else None,
                evidence_facts=[],
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
                tasks=[
                    dict(
                        id=t.id, title=t.title, status=t.status, primary_issue_id=t.primary_issue_id
                    )
                    for t in linked
                ],
                **result,
            )
        )
    signal_count = len(items)
    if issue_ids is None:
        items.extend(query_reviews(db, website_id, now))
    opportunity_count = len(items) - signal_count
    counts = Counter(item["lane"] for item in items)
    # Exact duplicate groups only; the raw signal counters stay unchanged.
    duplicate_ids = [
        evidence[i["issue_id"]].id
        for i in items
        if i["issue_type"] in {"duplicate_title", "duplicate_meta_description"}
        and i["issue_id"] in evidence
    ]
    duplicate_details = dict(read_evidence(db, duplicate_ids))
    from app.services.work_preview_groups import group_duplicates

    items = group_duplicates(items, evidence, duplicate_details)
    selected = [
        item
        for item in items
        if (include_history or lane == "history" or item["lane"] != "history")
        and (not lane or item["lane"] == lane)
        and q.casefold()
        in (
            item["title"]
            + " "
            + " ".join(member.get("url") or "" for member in item.get("members", [item]))
        ).casefold()
    ]
    selected.sort(
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}.get(item["severity"], 3),
            str(item["issue_id"]),
        )
    )
    visible = selected[offset : offset + limit]
    visible_ids = [item["issue_id"] for item in visible]
    # Load small allowlisted details only for the displayed issues, not all history.
    detail_ids = [evidence[i].id for i in visible_ids if i in evidence]
    details = dict(read_evidence(db, detail_ids))
    for item in visible:
        if item["issue_type"] == "query_content_review":
            continue
        item["evidence_facts"] = evidence_facts(
            item["issue_type"],
            details.get(evidence[item["issue_id"]].id, {}) if item["issue_id"] in evidence else {},
        )
    return dict(
        generated_at=now,
        rule_version="pilot-2",
        total_signals=signal_count,
        total_opportunities=opportunity_count,
        counts={key: counts[key] for key in LANES},
        total=len(selected),
        items=visible,
        lanes=LANES,
    )

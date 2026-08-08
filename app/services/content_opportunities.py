import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal
from app.models.content_analysis import (
    QueryContentClassification,
    UrlContentClassification,
    UrlContentOverride,
)
from app.models.discovery import Url
from app.models.integrations import SearchConsoleQueryMetric
from app.models.issues import ActivityLog
from app.models.recommendations import (
    RecommendationTask,
    RecommendationTaskEvent,
    RecommendationTaskUrl,
)
from app.models.website import Website
from app.services.content_analysis import CLASSIFICATION_VERSION, normalize_query
from app.services.recommendation_tasks import ACTIVE_TASK_STATUSES, actor_label

OPPORTUNITY_DEFINITION_VERSION = "content-opportunity-2026-08-07-v1"


def _key(kind: str, url_ids: list[UUID], evidence: object) -> str:
    payload = json.dumps(
        {"kind": kind, "urls": sorted(str(item) for item in url_ids), "evidence": evidence},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _latest_classifications(db: Session, website_id: UUID) -> dict[UUID, UrlContentClassification]:
    result: dict[UUID, UrlContentClassification] = {}
    rows = db.scalars(
        select(UrlContentClassification)
        .where(UrlContentClassification.website_id == website_id)
        .order_by(UrlContentClassification.created_at.desc())
    )
    for row in rows:
        result.setdefault(row.url_id, row)
    return result


def build_content_opportunities(
    db: Session, website_id: UUID, period_start: date, period_end: date
) -> dict[str, object]:
    website = db.get(Website, website_id)
    if not website:
        raise ValueError("Website not found")
    language = (website.language or "und").lower()
    country = (website.country or "ZZ").upper()
    classifications = _latest_classifications(db, website_id)
    urls = {url.id: url for url in db.scalars(select(Url).where(Url.website_id == website_id))}
    overrides = {
        item.url_id: item
        for item in db.scalars(
            select(UrlContentOverride).where(UrlContentOverride.website_id == website_id)
        )
    }
    website_distribution: Counter[str] = Counter()
    cluster_distribution: dict[str, Counter[str]] = defaultdict(Counter)
    pages: list[dict[str, object]] = []
    opportunities: list[dict[str, object]] = []
    for url_id, classification in classifications.items():
        url = urls.get(url_id)
        if not url:
            continue
        override = overrides.get(url_id)
        effective_intent = (
            override.search_intent
            if override and override.is_locked and override.search_intent
            else classification.search_intent
        )
        cluster = next(
            (part for part in urlsplit(url.normalized_url).path.split("/") if part),
            "/",
        )
        website_distribution[effective_intent] += 1
        cluster_distribution[cluster][effective_intent] += 1
        pages.append(
            {
                "url_id": str(url_id),
                "url": url.normalized_url,
                "cluster": cluster,
                "search_intent": effective_intent,
                "automatic_intent": classification.search_intent,
                "journey_stage": override.journey_stage
                if override and override.is_locked and override.journey_stage
                else classification.journey_stage,
                "content_role": override.content_role
                if override and override.is_locked and override.content_role
                else classification.content_role,
                "confidence": classification.confidence,
                "source_coverage": classification.source_coverage,
                "overridden": bool(override and override.is_locked),
            }
        )
        if (
            override
            and override.is_locked
            and override.search_intent
            and override.search_intent != classification.search_intent
            and classification.confidence >= 0.65
        ):
            evidence = {
                "automatic": classification.search_intent,
                "manual": override.search_intent,
                "confidence": classification.confidence,
            }
            opportunities.append(
                {
                    "key": _key("intent_mismatch", [url_id], evidence),
                    "type": "intent_mismatch",
                    "title": "Controleer verschil tussen gekozen en gemeten zoekintentie",
                    "description": (
                        "De gelockte handmatige keuze wijkt af van de actuele deterministische "
                        "classificatie. Controleer de pagina en het zoekbewijs voordat u wijzigt."
                    ),
                    "confidence": classification.confidence,
                    "url_ids": [str(url_id)],
                    "evidence": evidence,
                }
            )

    query_pages: dict[str, dict[UUID, dict[str, float]]] = defaultdict(
        lambda: defaultdict(lambda: {"clicks": 0.0, "impressions": 0.0})
    )
    rows = db.execute(
        select(
            SearchConsoleQueryMetric.query,
            SearchConsoleQueryMetric.url_id,
            SearchConsoleQueryMetric.clicks,
            SearchConsoleQueryMetric.impressions,
        ).where(
            SearchConsoleQueryMetric.website_id == website_id,
            SearchConsoleQueryMetric.date >= period_start,
            SearchConsoleQueryMetric.date <= period_end,
            SearchConsoleQueryMetric.url_id.is_not(None),
        )
    )
    for query, url_id, clicks, impressions in rows:
        totals = query_pages[normalize_query(str(query))][url_id]
        totals["clicks"] += float(clicks or 0)
        totals["impressions"] += float(impressions or 0)

    for query, per_url in query_pages.items():
        material = [
            (url_id, totals)
            for url_id, totals in per_url.items()
            if totals["impressions"] >= 50 and url_id in classifications
        ]
        total_impressions = sum(item[1]["impressions"] for item in material)
        query_classification = db.scalar(
            select(QueryContentClassification).where(
                QueryContentClassification.normalized_query == query,
                QueryContentClassification.language == language,
                QueryContentClassification.country == country,
                QueryContentClassification.classification_version == CLASSIFICATION_VERSION,
            )
        )
        if (
            material
            and total_impressions >= 75
            and query_classification
            and query_classification.search_intent not in {"uncertain", "mixed"}
            and all(
                classifications[url_id].confidence >= 0.65
                and classifications[url_id].search_intent != query_classification.search_intent
                for url_id, _ in material
            )
        ):
            gap_url_ids = [url_id for url_id, _ in material]
            gap_evidence = {
                "query": query,
                "query_intent": query_classification.search_intent,
                "page_intents": sorted(
                    {classifications[url_id].search_intent for url_id in gap_url_ids}
                ),
                "impressions": round(total_impressions),
            }
            opportunities.append(
                {
                    "key": _key("content_gap", gap_url_ids, gap_evidence),
                    "type": "content_gap",
                    "title": f"Controleer ontbrekende dekking voor ‘{query}’",
                    "description": (
                        "De gemeten zoekintentie wijkt af van alle gekoppelde pagina-intenties. "
                        "Controleer eerst of een bestaande pagina moet worden aangescherpt."
                    ),
                    "confidence": query_classification.confidence,
                    "url_ids": [str(item) for item in gap_url_ids],
                    "evidence": gap_evidence,
                }
            )
        if len(material) < 2 or total_impressions < 150:
            continue
        material.sort(key=lambda item: item[1]["impressions"], reverse=True)
        second_share = material[1][1]["impressions"] / total_impressions
        intents = {classifications[url_id].search_intent for url_id, _ in material}
        if second_share < 0.2 or "uncertain" in intents or len(intents) != 1:
            continue
        url_ids = [url_id for url_id, _ in material]
        evidence = {
            "query": query,
            "total_impressions": round(total_impressions),
            "second_page_share": round(second_share, 3),
            "intent": next(iter(intents)),
        }
        opportunities.append(
            {
                "key": _key("query_overlap", url_ids, evidence),
                "type": "query_overlap",
                "title": f"Controleer overlap voor zoekopdracht ‘{query}’",
                "description": (
                    "Meerdere pagina's ontvangen een materieel deel van dezelfde GSC-vertoningen "
                    "en hebben dezelfde waarschijnlijke intentie."
                ),
                "confidence": min(0.95, 0.6 + second_share),
                "url_ids": [str(item) for item in url_ids],
                "evidence": evidence,
            }
        )

    return {
        "period_start": period_start,
        "period_end": period_end,
        "coverage": {
            "classified_pages": len(pages),
            "pages_with_gsc": sum(
                1 for page in pages if page["source_coverage"].get("gsc_queries")
            ),
        },
        "website_distribution": dict(sorted(website_distribution.items())),
        "cluster_distribution": {
            cluster: dict(sorted(distribution.items()))
            for cluster, distribution in sorted(cluster_distribution.items())
        },
        "pages": pages,
        "opportunities": opportunities,
    }


def create_opportunity_task(
    db: Session,
    *,
    website_id: UUID,
    opportunity: dict[str, object],
    principal: Principal,
) -> tuple[RecommendationTask, bool]:
    opportunity_key = str(opportunity["key"])
    existing_tasks = db.scalars(
        select(RecommendationTask).where(
            RecommendationTask.website_id == website_id,
            RecommendationTask.recommendation_type == f"content_{opportunity['type']}",
            RecommendationTask.status.in_(ACTIVE_TASK_STATUSES),
        )
    )
    for task in existing_tasks:
        if task.verification_spec.get("opportunity_key") == opportunity_key:
            return task, False
    task = RecommendationTask(
        website_id=website_id,
        created_by_user_id=principal.user_id,
        recommendation_type=f"content_{opportunity['type']}",
        definition_version=OPPORTUNITY_DEFINITION_VERSION,
        title=str(opportunity["title"])[:255],
        category="content_opportunity",
        primary_role="content_editor",
        supporting_roles=["seo_specialist"],
        priority="normal",
        priority_reason=(
            "Uitlegbare contentkans met voldoende brondata; geen automatisch technisch defect."
        ),
        effort_confidence="low",
        feasibility="review_required",
        action=(
            "Controleer het bewijs en kies daarna bewust of en welke contentaanpassing nodig is."
        ),
        rationale=str(opportunity["description"]),
        steps=["Controleer zoekvraag en pagina's.", "Kies behoud, differentiatie of consolidatie."],
        acceptance_criteria=["De gekozen contentrol en onderbouwing zijn vastgelegd."],
        verification_spec={
            "opportunity_key": opportunity_key,
            "evidence": opportunity["evidence"],
            "automated_verification": False,
        },
    )
    db.add(task)
    db.flush()
    for url_id in opportunity["url_ids"]:
        db.add(RecommendationTaskUrl(task_id=task.id, url_id=UUID(str(url_id)), role="page"))
    label = actor_label(db, principal)
    db.add_all(
        [
            RecommendationTaskEvent(
                task_id=task.id,
                actor_user_id=principal.user_id,
                actor_label=label,
                event_type="created",
                new_status=task.status,
                details={"opportunity_key": opportunity_key},
            ),
            ActivityLog(
                website_id=website_id,
                actor=label,
                activity_type="content_opportunity_task_created",
                summary=f"Taak aangemaakt: {task.title}",
                details={"task_id": str(task.id), "opportunity_key": opportunity_key},
            ),
        ]
    )
    db.commit()
    db.refresh(task)
    return task, True


def create_question_gap_task(
    db: Session,
    *,
    website_id: UUID,
    url_id: UUID,
    question: str,
    summary: str,
    recommended_action: str,
    observation_id: UUID,
    principal: Principal,
) -> tuple[RecommendationTask, bool]:
    """Create one active content task for a measured question/page gap."""
    normalized_question = " ".join(question.lower().split())
    scope_key = f"{url_id}:{normalized_question}"
    existing_tasks = db.scalars(
        select(RecommendationTask).where(
            RecommendationTask.website_id == website_id,
            RecommendationTask.recommendation_type == "content_question_gap",
            RecommendationTask.status.in_(ACTIVE_TASK_STATUSES),
        )
    )
    for task in existing_tasks:
        if task.verification_spec.get("scope_key") == scope_key:
            return task, False
    task = RecommendationTask(
        website_id=website_id,
        created_by_user_id=principal.user_id,
        recommendation_type="content_question_gap",
        definition_version=OPPORTUNITY_DEFINITION_VERSION,
        title=f"Beantwoord de vraag: {question}"[:255],
        category="content_opportunity",
        primary_role="content_editor",
        supporting_roles=["seo_specialist"],
        priority="normal",
        priority_reason="Relevante zoekvraag met crawlbewijs en een begrensde externe waarneming.",
        effort_confidence="low",
        feasibility="review_required",
        action=recommended_action,
        rationale=summary,
        steps=[
            "Controleer of de vraag bij de rol van deze pagina past.",
            "Voeg of verbeter het antwoord volgens het advies.",
            "Meld de taak gereed voor controle in de normale taakworkflow.",
        ],
        acceptance_criteria=[
            "De vraag wordt direct, specifiek en inhoudelijk controleerbaar beantwoord.",
            "De aanpassing past bij de rol van de pagina en bevat geen onbewezen claims.",
        ],
        verification_spec={
            "scope_key": scope_key,
            "question": question,
            "observation_id": str(observation_id),
            "automated_verification": False,
        },
    )
    db.add(task)
    db.flush()
    db.add(RecommendationTaskUrl(task_id=task.id, url_id=url_id, role="page"))
    label = actor_label(db, principal)
    db.add_all(
        [
            RecommendationTaskEvent(
                task_id=task.id,
                actor_user_id=principal.user_id,
                actor_label=label,
                event_type="created",
                new_status=task.status,
                details={"scope_key": scope_key},
            ),
            ActivityLog(
                website_id=website_id,
                actor=label,
                activity_type="content_question_gap_task_created",
                summary=f"Taak aangemaakt: {task.title}",
                details={"task_id": str(task.id), "url_id": str(url_id)},
            ),
        ]
    )
    db.commit()
    db.refresh(task)
    return task, True

"""Stored query evidence prompts content review, never an automatic FAQ claim."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.discovery import Url
from app.models.integrations import SearchConsoleQueryMetric as Metric
from app.models.recommendations import RecommendationTask, RecommendationTaskUrl


def query_reviews(db: Session, website_id: UUID, now: datetime) -> list[dict]:
    end = db.scalar(
        select(func.max(Metric.date)).where(
            Metric.website_id == website_id, Metric.date <= now.date()
        )
    )
    if not end:
        return []
    start = end - timedelta(days=27)
    grouped = (
        select(
            Metric.url_id,
            Metric.query,
            func.sum(Metric.impressions).label("impressions"),
            func.sum(Metric.clicks).label("clicks"),
        )
        .join(Url, Url.id == Metric.url_id)
        .where(
            Metric.website_id == website_id,
            Url.website_id == website_id,
            Metric.date >= start,
            Metric.date <= end,
        )
        .group_by(Metric.url_id, Metric.query)
        .subquery()
    )
    ranked = select(
        grouped,
        func.row_number()
        .over(
            partition_by=grouped.c.url_id, order_by=(grouped.c.impressions.desc(), grouped.c.query)
        )
        .label("n"),
    ).subquery()
    rows = db.execute(
        select(ranked, Url.normalized_url)
        .join(Url, Url.id == ranked.c.url_id)
        .where(ranked.c.n <= 3, ranked.c.impressions >= 75)
    ).all()
    by_url: dict = {}
    for row in rows:
        by_url.setdefault(row.url_id, []).append(row)
    if not by_url:
        return []
    linked: dict = {}
    for url_id, task in db.execute(
        select(RecommendationTaskUrl.url_id, RecommendationTask)
        .join(RecommendationTask, RecommendationTask.id == RecommendationTaskUrl.task_id)
        .where(
            RecommendationTask.website_id == website_id, RecommendationTaskUrl.url_id.in_(by_url)
        )
    ):
        linked.setdefault(url_id, []).append(dict(id=task.id, title=task.title, status=task.status))
    result = []
    for url_id, queries in by_url.items():
        queries.sort(key=lambda row: (-row.impressions, row.query))
        stale = end < now.date() - timedelta(days=7)
        tasks = linked.get(url_id, [])
        result.append(
            dict(
                issue_id=f"query:{url_id}",
                title="Beoordeel antwoorden op gemeten zoekvragen",
                issue_type="query_content_review",
                url=queries[0].normalized_url,
                severity="low",
                status="voorstel",
                description=(
                    "GSC-zoekvragen zijn aanleiding voor beoordeling. De cijfers bewijzen"
                    " geen ontbrekend antwoord of te verwachten groei."
                ),
                lane="opportunity",
                reason=(
                    (
                        "De opgeslagen zoekperiode is ouder dan zeven dagen; actualiseer "
                        "eerst de zoekgegevens. "
                    )
                    if stale
                    else ""
                )
                + (
                    "Vergelijk de gemeten zoekvragen met de bestaande antwoorden en de "
                    "functie van deze pagina."
                ),
                first_step=("Actualiseer eerst de zoekgegevens. " if stale else "")
                + (
                    "Selecteer passende zoekvragen en noteer welke de pagina al "
                    "beantwoordt en welke aanvulling bezoekers helpt. Bepaal pas daarna "
                    "of tekst, een uitlegblok of een FAQ nodig is."
                ),
                role="SEO-manager → redactie; webbouwer alleen bij ontbrekende functionaliteit",
                completion=(
                    "De passende vragen, bestaande antwoorden en gekozen aanvullingen "
                    "zijn vastgelegd. Is een nieuw blok nodig, laat de webbouwer dit "
                    "eerst beschikbaar maken; daarna vult de redactie het en volgt "
                    "controle. Zonder inhoudelijke lacune volgt geen wijzigingsopdracht."
                ),
                current_evidence=False,
                evidence_code="query_review",
                evidence_reason="Zoekgegevens zijn geen bewijs van een inhoudelijke lacune.",
                evidence_at=None,
                snapshot_id=None,
                latest_checked_at=None,
                analysis_checked_at=None,
                evidence_facts=[
                    f"Zoekperiode: {start} t/m {end}. "
                    "Maximaal drie zoekvragen met elk minstens 75 vertoningen; "
                    "geen volledige pagina-totalen."
                ]
                + [
                    f"{row.query[:300]} — {round(row.impressions)} vertoningen, "
                    f"{round(row.clicks)} klikken"
                    for row in queries
                ],
                tasks=tasks,
                task_context=(
                    "Bestaande taken op deze pagina; controleer of ze deze zoekvragen al "
                    "behandelen."
                )
                if tasks
                else None,
            )
        )
    return result

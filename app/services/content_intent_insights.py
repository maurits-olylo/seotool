import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crawl import UrlSnapshot
from app.models.integrations import SearchConsoleQueryMetric
from app.models.website import Website

STOPWORDS = {
    "aan",
    "als",
    "bij",
    "de",
    "een",
    "en",
    "het",
    "in",
    "is",
    "met",
    "naar",
    "of",
    "om",
    "op",
    "te",
    "van",
    "voor",
    "wat",
    "welke",
    "wie",
    "waar",
    "wanneer",
    "waarom",
    "hoe",
}
QUESTION_WORDS = {"hoe", "wat", "waarom", "wanneer", "welke", "waar", "kan", "mag"}
INTENT_TERMS = {
    "prijs": {"kost", "prijs", "tarief", "offerte"},
    "vergelijking": {"verschil", "vergelijk", "versus", "beter"},
    "werkwijze": {"monteer", "plaats", "vervang", "onderhoud", "repareer"},
    "geschiktheid": {"geschikt", "mogelijk", "kan", "mag"},
}


@dataclass
class QueryTotals:
    page_url: str
    url_id: UUID
    clicks: float = 0
    impressions: int = 0
    position_weight: float = 0

    @property
    def position(self) -> float:
        return self.position_weight / self.impressions if self.impressions else 0


def _stem(token: str) -> str:
    if len(token) > 5 and token.endswith("en"):
        return token[:-2]
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token


def _tokens(value: str | None, *, remove_stopwords: bool = True) -> set[str]:
    plain = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    words = {_stem(item) for item in re.findall(r"[a-z0-9]+", plain.lower())}
    return words - STOPWORDS if remove_stopwords else words


def _intent(query: str) -> tuple[str | None, set[str]]:
    all_tokens = _tokens(query, remove_stopwords=False)
    for label, terms in INTENT_TERMS.items():
        matched = all_tokens & terms
        if matched:
            return label, matched
    first_word = next(iter(re.findall(r"[a-z0-9]+", query.lower())), "")
    if first_word in QUESTION_WORDS:
        return "vraag", set()
    return None, set()


def _latest_snapshots(db: Session, url_ids: set[UUID]) -> dict[UUID, UrlSnapshot]:
    snapshots: dict[UUID, UrlSnapshot] = {}
    if not url_ids:
        return snapshots
    rows = db.scalars(
        select(UrlSnapshot)
        .where(UrlSnapshot.url_id.in_(url_ids))
        .order_by(UrlSnapshot.checked_at.desc())
    )
    for snapshot in rows:
        snapshots.setdefault(snapshot.url_id, snapshot)
    return snapshots


def _snapshot_text(snapshot: UrlSnapshot) -> tuple[set[str], set[str]]:
    headings = snapshot.headings or {}
    heading_text = " ".join(
        str(value)
        for values in headings.values()
        for value in (values if isinstance(values, list) else [])
    )
    prominent = _tokens(" ".join([snapshot.title or "", heading_text]))
    full = prominent | _tokens(snapshot.meta_description) | _tokens(snapshot.main_content)
    return prominent, full


def build_content_intent_insights(
    db: Session,
    website_id: UUID,
    start: date,
    end: date,
) -> list[dict[str, object]]:
    """Find material GSC questions that are not clearly covered by their landing page."""
    website = db.get(Website, website_id)
    brand_tokens = _tokens(website.name if website else "")
    totals: dict[tuple[str, UUID], QueryTotals] = {}
    rows = db.execute(
        select(
            SearchConsoleQueryMetric.query,
            SearchConsoleQueryMetric.page_url,
            SearchConsoleQueryMetric.url_id,
            SearchConsoleQueryMetric.clicks,
            SearchConsoleQueryMetric.impressions,
            SearchConsoleQueryMetric.position,
        ).where(
            SearchConsoleQueryMetric.website_id == website_id,
            SearchConsoleQueryMetric.date >= start,
            SearchConsoleQueryMetric.date <= end,
            SearchConsoleQueryMetric.url_id.is_not(None),
        )
    )
    for query, page_url, url_id, clicks, impressions, position in rows:
        key = (str(query), url_id)
        item = totals.setdefault(key, QueryTotals(str(page_url), url_id))
        item.clicks += float(clicks or 0)
        item.impressions += int(impressions or 0)
        item.position_weight += float(position or 0) * int(impressions or 0)

    candidates = [
        (item.impressions, query, item)
        for (query, _), item in totals.items()
        if item.impressions >= 75 and 5 <= item.position <= 30 and _intent(query)[0]
    ]
    snapshots = _latest_snapshots(db, {item.url_id for _, _, item in candidates})
    insights: list[tuple[float, dict[str, object]]] = []
    for _, query, item in candidates:
        query_tokens = _tokens(query)
        if brand_tokens and query_tokens and query_tokens <= brand_tokens:
            continue
        snapshot = snapshots.get(item.url_id)
        if not snapshot or not snapshot.main_content or (snapshot.word_count or 0) < 50:
            continue
        label, intent_terms = _intent(query)
        prominent, full = _snapshot_text(snapshot)
        subject_tokens = query_tokens - intent_terms
        subject_coverage = len(subject_tokens & full) / len(subject_tokens) if subject_tokens else 1
        missing_intent = bool(intent_terms and not (intent_terms & full))
        prominent_coverage = (
            len(subject_tokens & prominent) / len(subject_tokens) if subject_tokens else 1
        )
        if not missing_intent and subject_coverage >= 0.6 and prominent_coverage >= 0.5:
            continue

        if missing_intent or subject_coverage < 0.6:
            confidence = "hoog"
            reason = (
                f"De gecrawlde inhoud dekt het onderwerp voor {subject_coverage * 100:.0f}%"
                + (f" en bevat geen duidelijk {label}-signaal" if missing_intent else "")
                + "."
            )
        else:
            confidence = "middel"
            reason = "Het onderwerp staat in de tekst, maar niet duidelijk in title of koppen."
        host_path = urlsplit(item.page_url).path or "/"
        insight = {
            "type": "content_intent_gap",
            "source": "Google Search Console + crawl",
            "title": f"Mogelijk onbeantwoorde zoekvraag: “{query}”",
            "description": (
                f"{item.impressions:,} vertoningen, {item.clicks:,.0f} klikken en "
                f"gemiddelde positie {item.position:.1f}. {reason}"
            ),
            "query": query,
            "url": item.page_url,
            "page_path": host_path,
            "intent": label,
            "confidence": confidence,
            "clicks": round(item.clicks, 1),
            "impressions": item.impressions,
            "position": round(item.position, 1),
            "subject_coverage_percent": round(subject_coverage * 100),
            "recommended_action": (
                "Controleer de zoekintentie en voeg alleen een direct antwoord toe als dit "
                "inhoudelijk bij deze pagina hoort; kies anders een geschiktere landingspagina."
            ),
        }
        score = item.impressions / max(item.position, 1) * (1.5 if confidence == "hoog" else 1)
        insights.append((score, insight))

    return [item for _, item in sorted(insights, key=lambda row: row[0], reverse=True)[:5]]

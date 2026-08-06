import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.content_analysis import (
    ContentAnalysisSettings,
    QueryContentClassification,
    UrlContentClassification,
)
from app.models.crawl import UrlSnapshot
from app.models.discovery import Url
from app.models.integrations import SearchConsoleQueryMetric
from app.models.website import Website
from app.services.content_classification import validate_probabilities
from app.services.url_normalization import InvalidUrlError, NormalizationOptions, normalize_url

CLASSIFICATION_VERSION = "intent-rules-2026-08-07-v1"
INTENT_TERMS: dict[str, set[str]] = {
    "informational": {"how", "what", "why", "guide", "uitleg", "hoe", "wat", "waarom"},
    "commercial": {"best", "compare", "review", "comparison", "beste", "vergelijk", "ervaring"},
    "transactional": {
        "buy",
        "order",
        "book",
        "quote",
        "koop",
        "bestel",
        "boek",
        "offerte",
        "prijs",
    },
    "trust": {
        "about",
        "case",
        "certified",
        "testimonial",
        "over",
        "keurmerk",
        "referentie",
        "ervaringen",
    },
    "navigational": {"login", "contact", "portal", "inloggen", "adres", "telefoon"},
}
INTENT_CONTEXT = {
    "informational": ("understand", "attract"),
    "commercial": ("compare", "support_choice"),
    "transactional": ("act", "convert"),
    "trust": ("consider", "provide_proof"),
    "navigational": ("act", "navigate"),
    "mixed": ("uncertain", "uncertain"),
    "uncertain": ("uncertain", "uncertain"),
}


@dataclass(frozen=True)
class ClassificationResult:
    search_intent: str
    journey_stage: str
    content_role: str
    confidence: float
    probabilities: dict[str, float]
    evidence: list[dict[str, object]]


def normalize_query(query: str) -> str:
    plain = unicodedata.normalize("NFKC", query).lower()
    return " ".join(plain.split())


def _tokens(value: str) -> set[str]:
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return set(re.findall(r"[a-z0-9]+", plain.lower()))


def _result(scores: dict[str, float], evidence: list[dict[str, object]]) -> ClassificationResult:
    positive = {label: score for label, score in scores.items() if score > 0}
    if not positive:
        probabilities = {"uncertain": 1.0}
        intent = "uncertain"
    else:
        total = sum(positive.values())
        probabilities = {label: round(score / total, 6) for label, score in positive.items()}
        difference = 1.0 - sum(probabilities.values())
        winner = max(probabilities, key=probabilities.get)  # type: ignore[arg-type]
        probabilities[winner] = round(probabilities[winner] + difference, 6)
        ordered = sorted(probabilities.items(), key=lambda item: item[1], reverse=True)
        intent = "mixed" if len(ordered) > 1 and ordered[0][1] - ordered[1][1] < 0.15 else winner
    validate_probabilities(probabilities)
    confidence = max(probabilities.values()) if intent not in {"mixed", "uncertain"} else 0.4
    journey_stage, content_role = INTENT_CONTEXT[intent]
    return ClassificationResult(
        intent,
        journey_stage,
        content_role,
        round(confidence, 3),
        probabilities,
        evidence,
    )


def classify_query(query: str, branded_terms: list[str] | None = None) -> ClassificationResult:
    normalized = normalize_query(query)
    tokens = _tokens(normalized)
    scores = defaultdict(float)
    evidence: list[dict[str, object]] = []
    for intent, terms in INTENT_TERMS.items():
        matched = sorted(tokens & terms)
        if matched:
            scores[intent] += len(matched)
            evidence.append({"source": "query_terms", "intent": intent, "matched": matched})
    for brand in branded_terms or []:
        if normalize_query(brand) in normalized:
            scores["navigational"] += 1.5
            evidence.append({"source": "branded_term", "intent": "navigational"})
            break
    return _result(dict(scores), evidence)


def classify_page(snapshot: UrlSnapshot, query_weights: dict[str, float]) -> ClassificationResult:
    headings = " ".join(
        str(item)
        for values in (snapshot.headings or {}).values()
        for item in (values if isinstance(values, list) else [])
    )
    prominent = " ".join((snapshot.requested_url, snapshot.title or "", headings))
    body = " ".join((snapshot.meta_description or "", snapshot.main_content or ""))
    prominent_tokens = _tokens(prominent)
    body_tokens = _tokens(body)
    scores = defaultdict(float, query_weights)
    evidence: list[dict[str, object]] = []
    for intent, terms in INTENT_TERMS.items():
        strong = sorted(prominent_tokens & terms)
        weak = sorted((body_tokens & terms) - set(strong))
        if strong or weak:
            scores[intent] += len(strong) * 2 + len(weak) * 0.5
            evidence.append(
                {"source": "page_content", "intent": intent, "prominent": strong, "body": weak}
            )
    if query_weights:
        evidence.append({"source": "gsc_queries", "weights": query_weights})
    return _result(dict(scores), evidence)


def _input_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def analyze_website_content(
    db: Session, website_id: UUID, period_start: date, period_end: date
) -> dict[str, int]:
    website = db.get(Website, website_id)
    if not website:
        raise ValueError("Website not found")
    settings = db.get(ContentAnalysisSettings, website_id)
    branded_terms = settings.branded_terms if settings else []
    language = (website.language or "und").lower()
    country = (website.country or "ZZ").upper()
    query_weights: dict[UUID, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    query_rows = db.execute(
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
    queries_classified = 0
    for query, url_id, clicks, impressions in query_rows:
        normalized = normalize_query(str(query))
        cached = db.scalar(
            select(QueryContentClassification).where(
                QueryContentClassification.normalized_query == normalized,
                QueryContentClassification.language == language,
                QueryContentClassification.country == country,
                QueryContentClassification.classification_version == CLASSIFICATION_VERSION,
            )
        )
        if not cached:
            result = classify_query(normalized)
            cached = QueryContentClassification(
                normalized_query=normalized,
                language=language,
                country=country,
                classification_version=CLASSIFICATION_VERSION,
                input_hash=_input_hash({"query": normalized}),
                search_intent=result.search_intent,
                journey_stage=result.journey_stage,
                content_role=result.content_role,
                confidence=result.confidence,
                probabilities=result.probabilities,
                evidence=result.evidence,
            )
            db.add(cached)
            queries_classified += 1
        weight = max(float(impressions or 0), 1.0) + float(clicks or 0) * 2
        for intent, probability in cached.probabilities.items():
            query_weights[url_id][intent] += weight * probability
        if any(normalize_query(term) in normalized for term in branded_terms):
            query_weights[url_id]["navigational"] += weight * 1.5

    urls = list(
        db.scalars(
            select(Url).where(
                Url.website_id == website_id,
                Url.is_active.is_(True),
                Url.is_indexable.is_(True),
                Url.current_status_code.between(200, 299),
            )
        )
    )
    pages_created = 0
    pages_unchanged = 0
    for url in urls:
        snapshot = db.scalar(
            select(UrlSnapshot)
            .where(UrlSnapshot.url_id == url.id, UrlSnapshot.content_type.ilike("text/html%"))
            .order_by(UrlSnapshot.checked_at.desc())
            .limit(1)
        )
        if not snapshot or not snapshot.main_content_hash:
            continue
        if snapshot.canonical:
            try:
                options = NormalizationOptions(
                    ignored_query_parameters=frozenset(
                        website.settings.ignored_query_parameters if website.settings else []
                    )
                )
                if normalize_url(snapshot.canonical, options=options) != url.normalized_url:
                    continue
            except InvalidUrlError:
                continue
        weights = dict(query_weights.get(url.id, {}))
        input_hash = _input_hash(
            {
                "snapshot": snapshot.main_content_hash,
                "metadata": snapshot.metadata_hash,
                "queries": weights,
                "period": [period_start.isoformat(), period_end.isoformat()],
            }
        )
        existing = db.scalar(
            select(UrlContentClassification).where(
                UrlContentClassification.url_id == url.id,
                UrlContentClassification.input_hash == input_hash,
                UrlContentClassification.classification_version == CLASSIFICATION_VERSION,
            )
        )
        if existing:
            pages_unchanged += 1
            continue
        result = classify_page(snapshot, weights)
        db.add(
            UrlContentClassification(
                website_id=website_id,
                url_id=url.id,
                period_start=period_start,
                period_end=period_end,
                input_hash=input_hash,
                classification_version=CLASSIFICATION_VERSION,
                search_intent=result.search_intent,
                journey_stage=result.journey_stage,
                content_role=result.content_role,
                confidence=result.confidence,
                probabilities=result.probabilities,
                source_coverage={"crawl": True, "gsc_queries": bool(weights)},
                evidence=result.evidence,
            )
        )
        pages_created += 1
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    return {
        "queries_classified": queries_classified,
        "pages_created": pages_created,
        "pages_unchanged": pages_unchanged,
    }

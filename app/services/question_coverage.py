import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

CoverageStatus = Literal["answered", "partial", "implicit", "missing"]

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
INTENT_TERMS = {
    "price": {"kost", "prijs", "tarief", "offerte", "euro"},
    "comparison": {"verschil", "vergelijk", "versus", "beter"},
    "method": {"monteer", "plaats", "vervang", "onderhoud", "repareer"},
    "suitability": {"geschikt", "mogelijk", "kan", "mag"},
}
QUESTION_WORDS = {
    "hoe",
    "wat",
    "waarom",
    "wanneer",
    "welke",
    "waar",
    "wie",
    "kan",
    "kunnen",
    "mag",
    "moet",
    "zijn",
}


@dataclass(frozen=True)
class QuestionCoverageResult:
    status: CoverageStatus
    confidence: str
    subject_coverage: float
    prominent_coverage: float
    passage_coverage: float
    intent: str | None
    missing_terms: tuple[str, ...]
    best_passage: str | None
    evidence: tuple[dict[str, object], ...]
    recommended_action: str


def _stem(token: str) -> str:
    if len(token) > 5 and token.endswith("en"):
        return token[:-2]
    return token


def tokens(value: str | None, *, remove_stopwords: bool = True) -> set[str]:
    plain = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    words = {_stem(item) for item in re.findall(r"[a-z0-9]+", plain.lower())}
    return words - STOPWORDS if remove_stopwords else words


def question_intent(question: str) -> tuple[str | None, set[str]]:
    all_tokens = tokens(question, remove_stopwords=False)
    for label, terms in INTENT_TERMS.items():
        matched = all_tokens & terms
        if matched:
            return label, matched
    return None, set()


def is_question_like(value: str) -> bool:
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    first_word = next(iter(re.findall(r"[a-z0-9]+", normalized)), "")
    intent, _ = question_intent(normalized)
    return first_word in QUESTION_WORDS or intent is not None


def _passages(content: str) -> list[str]:
    return [
        passage.strip() for passage in re.split(r"(?<=[.!?])\s+|\n+", content) if passage.strip()
    ]


def _coverage(subject: set[str], observed: set[str]) -> float:
    return len(subject & observed) / len(subject) if subject else 1.0


def _advice(status: CoverageStatus, intent: str | None, missing_terms: tuple[str, ...]) -> str:
    if status == "implicit":
        return (
            "Maak het bestaande antwoord expliciet en vindbaar met een passende tussenkop en een "
            "directe openingszin; voeg geen nieuw onderdeel toe als de informatie al compleet is."
        )
    if status == "partial":
        detail = f" Ontbrekende onderwerpen: {', '.join(missing_terms)}." if missing_terms else ""
        return (
            "Vul het bestaande antwoord aan met de ontbrekende beslisinformatie en laat feitelijke "
            f"claims inhoudelijk controleren.{detail}"
        )
    intent_hint = {
        "price": "prijsopbouw, bandbreedte en bepalende factoren",
        "comparison": "de relevante verschillen, situaties en afwegingen",
        "method": "de stappen, voorwaarden en praktische aandachtspunten",
        "suitability": "voor wie of wanneer dit wel en niet geschikt is",
    }.get(intent, "een direct, specifiek en controleerbaar antwoord")
    return (
        f"Voeg alleen op deze pagina een antwoord toe als de vraag bij haar rol past. Behandel dan "
        f"{intent_hint}; verwijs anders naar of maak een geschiktere landingspagina."
    )


def assess_question_coverage(
    question: str,
    *,
    title: str | None,
    headings: dict[str, list[str]] | None,
    meta_description: str | None,
    main_content: str | None,
) -> QuestionCoverageResult:
    """Conservatively assess whether visible page content answers one relevant question."""
    intent, question_intent_terms = question_intent(question)
    intent_terms = INTENT_TERMS.get(intent or "", set())
    subject = tokens(question) - question_intent_terms
    heading_text = " ".join(
        str(value)
        for values in (headings or {}).values()
        for value in (values if isinstance(values, list) else [])
    )
    prominent = tokens(" ".join((title or "", heading_text)))
    content = " ".join((meta_description or "", main_content or "")).strip()
    full = prominent | tokens(content)
    subject_coverage = _coverage(subject, full)
    prominent_coverage = _coverage(subject, prominent)
    intent_present = not intent_terms or bool(intent_terms & full)
    prominent_has_intent = not intent_terms or bool(intent_terms & prominent)

    ranked_passages = sorted(
        ((_coverage(subject, tokens(passage)), passage) for passage in _passages(content)),
        key=lambda item: item[0],
        reverse=True,
    )
    passage_coverage, best_passage = ranked_passages[0] if ranked_passages else (0.0, None)
    passage_has_intent = bool(
        best_passage and (not intent_terms or intent_terms & tokens(best_passage))
    )
    passage_is_substantial = bool(
        best_passage and len(tokens(best_passage, remove_stopwords=False)) >= 6
    )
    substantial_intent_passage = any(
        len(tokens(passage, remove_stopwords=False)) >= 6
        and (not intent_terms or bool(intent_terms & tokens(passage)))
        for _, passage in ranked_passages
    )

    if subject_coverage < 0.6 or not intent_present:
        status: CoverageStatus = "missing"
        confidence = "high"
    elif (
        passage_coverage >= 0.75
        and passage_has_intent
        and passage_is_substantial
        or prominent_coverage >= 0.75
        and prominent_has_intent
        and substantial_intent_passage
    ):
        status = "answered"
        confidence = "high" if prominent_coverage >= 0.5 else "medium"
    elif passage_coverage >= 0.6 and passage_is_substantial:
        status = "partial"
        confidence = "medium"
    elif intent_present and not (passage_has_intent and passage_coverage >= 0.6):
        status = "implicit"
        confidence = "medium"
    else:
        status = "partial"
        confidence = "low"

    missing_terms = tuple(sorted(subject - full))
    evidence = (
        {
            "source": "crawl",
            "subject_coverage": round(subject_coverage, 3),
            "prominent_coverage": round(prominent_coverage, 3),
            "passage_coverage": round(passage_coverage, 3),
            "intent_present": intent_present,
        },
    )
    return QuestionCoverageResult(
        status=status,
        confidence=confidence,
        subject_coverage=round(subject_coverage, 3),
        prominent_coverage=round(prominent_coverage, 3),
        passage_coverage=round(passage_coverage, 3),
        intent=intent,
        missing_terms=missing_terms,
        best_passage=best_passage,
        evidence=evidence,
        recommended_action=_advice(status, intent, missing_terms),
    )

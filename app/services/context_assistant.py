from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.discovery import Url
from app.models.integrations import GoogleAnalyticsMetric, MatomoPageMetric
from app.models.issues import Issue, IssueOccurrence
from app.models.opportunities import OpportunityEvaluation
from app.models.website import Website
from app.services.analytics_provider import AnalyticsPageTotal
from app.services.analytics_quality import AnalyticsAnomaly, quality_aware_analytics_totals
from app.services.issue_guidance import build_issue_guidance

OUT_OF_SCOPE_MARKERS = {
    "concurrent",
    "semrush",
    "ahrefs",
    "moz",
    "andere tool",
    "beste seo tool",
    "marktvergelijking",
}


class ContextAssistantError(ValueError):
    pass


@dataclass(frozen=True)
class ComparisonPeriod:
    label: str
    start: date
    end: date
    source: str | None
    rows: list[AnalyticsPageTotal]
    covered: bool
    configured: bool
    anomalies: list[AnalyticsAnomaly]

    @property
    def suspicious_conversions(self) -> float:
        return sum(item.events for item in self.anomalies)


def answer_context_question(
    db: Session,
    *,
    website_id: UUID,
    context_type: str,
    context_id: UUID,
    question: str,
    period_end: date | None = None,
    days: int = 28,
) -> dict[str, object]:
    if any(marker in question.casefold() for marker in OUT_OF_SCOPE_MARKERS):
        return _scope_limited_answer()
    if context_type == "issue":
        return _answer_issue(db, website_id=website_id, issue_id=context_id)
    if context_type == "opportunity_evaluation":
        return _answer_opportunity(db, website_id=website_id, evaluation_id=context_id)
    if context_type == "website_performance":
        if context_id != website_id:
            raise ContextAssistantError("Contextrecord niet gevonden.")
        if period_end is None:
            raise ContextAssistantError("Voor een periodevergelijking is period_end verplicht.")
        return _answer_website_performance(
            db, website_id=website_id, period_end=period_end, days=days
        )
    raise ContextAssistantError("Dit contexttype wordt niet ondersteund.")


def _answer_issue(db: Session, *, website_id: UUID, issue_id: UUID) -> dict[str, object]:
    issue = db.get(Issue, issue_id)
    if issue is None or issue.website_id != website_id:
        raise ContextAssistantError("Contextrecord niet gevonden.")
    occurrence = db.scalar(
        select(IssueOccurrence)
        .where(IssueOccurrence.issue_id == issue.id)
        .order_by(desc(IssueOccurrence.detected_at))
        .limit(1)
    )
    url = db.get(Url, issue.url_id) if issue.url_id else None
    evidence = occurrence.evidence if occurrence else {}
    guidance = build_issue_guidance(issue, evidence)
    facts = [
        f"Signaal: {issue.title}",
        f"Status: {issue.status}; ernst: {issue.severity}; confidence: {issue.confidence}.",
        f"Laatst gedetecteerd: {issue.last_detected_at.isoformat()}.",
    ]
    if url:
        facts.append(f"Betrokken URL: {url.normalized_url}")
    interpretations = [str(guidance["relevance"]["text"])]
    likely_cause = guidance.get("likely_cause")
    if isinstance(likely_cause, dict) and likely_cause.get("text"):
        interpretations.append(f"Waarschijnlijke verklaring: {likely_cause['text']}")
    missing = (
        []
        if occurrence
        else ["Er is geen afzonderlijk meetrecord met technisch bewijs beschikbaar."]
    )
    answer = (
        f"SEO Monitor heeft ‘{issue.title}’ gemeten met confidence {issue.confidence}. "
        f"Aanbevolen vervolgstap: {issue.recommended_action} "
        f"Controle: {guidance['verification']}"
    )
    sources = [
        {
            "source_type": "issue",
            "record_id": issue.id,
            "measured_at": issue.last_detected_at,
            "description": "Actueel issue en lifecycle-status",
        }
    ]
    if occurrence:
        sources.append(
            {
                "source_type": "issue_occurrence",
                "record_id": occurrence.id,
                "measured_at": occurrence.detected_at,
                "description": "Nieuwste opgeslagen waarneming",
            }
        )
    return {
        "status": "answered" if occurrence else "insufficient_evidence",
        "answer": answer,
        "facts": facts,
        "interpretations": interpretations,
        "missing_evidence": missing,
        "confidence": issue.confidence if occurrence else "low",
        "sources": sources,
        "mutations_performed": False,
    }


def _answer_opportunity(db: Session, *, website_id: UUID, evaluation_id: UUID) -> dict[str, object]:
    evaluation = db.get(OpportunityEvaluation, evaluation_id)
    if evaluation is None or evaluation.website_id != website_id:
        raise ContextAssistantError("Contextrecord niet gevonden.")
    pattern = str(evaluation.source_coverage.get("pattern") or "onbekend patroon")
    score = (
        f"{evaluation.total_score:.1f}/100" if evaluation.total_score is not None else "onbekend"
    )
    facts = [
        f"Patroon: {pattern}",
        f"Kansscore: {score}; prioriteitsklasse: {evaluation.priority_class}.",
        (
            f"Meetperiode: {evaluation.period_start.isoformat()} tot "
            f"{evaluation.period_end.isoformat()}."
        ),
        f"Formuleversie: {evaluation.formula_version}.",
    ]
    missing = [
        f"Bron {name} ontbreekt en is niet als nul meegerekend."
        for name, available in evaluation.source_coverage.items()
        if name != "pattern" and available is False
    ]
    dimensions = {
        "potentieel": evaluation.potential_score,
        "frictie": evaluation.friction_score,
        "bewijs": evaluation.evidence_score,
        "uitvoerbaarheid": evaluation.feasibility_score,
    }
    missing.extend(
        f"De deelscore {name} is onbekend." for name, value in dimensions.items() if value is None
    )
    interpretation = (
        "Dit is een uitlegbare prioritering van opgeslagen signalen, geen voorspelling van extra "
        "verkeer en geen algemene SEO-score."
    )
    return {
        "status": "answered" if evaluation.total_score is not None else "insufficient_evidence",
        "answer": (
            f"Deze {pattern}-beoordeling heeft een kansscore van {score}. "
            f"De uitkomst is geclassificeerd als {evaluation.priority_class}; "
            "controleer de bijdragers en ontbrekende bronnen vóór uitvoering."
        ),
        "facts": facts,
        "interpretations": [interpretation],
        "missing_evidence": missing,
        "confidence": _opportunity_confidence(evaluation.evidence_score),
        "sources": [
            {
                "source_type": "opportunity_evaluation",
                "record_id": evaluation.id,
                "measured_at": evaluation.created_at,
                "description": "Historische kansbeoordeling met formule- en brondekking",
            }
        ],
        "mutations_performed": False,
    }


def _opportunity_confidence(evidence_score: float | None) -> str:
    if evidence_score is None or evidence_score < 40:
        return "low"
    if evidence_score < 70:
        return "medium"
    return "high"


def _answer_website_performance(
    db: Session, *, website_id: UUID, period_end: date, days: int
) -> dict[str, object]:
    website = db.get(Website, website_id)
    if website is None:
        raise ContextAssistantError("Contextrecord niet gevonden.")
    current_start = period_end - timedelta(days=days - 1)
    previous_end = current_start - timedelta(days=1)
    previous_year_end = _shift_year(period_end, -1)
    two_years_ago_end = _shift_year(period_end, -2)
    periods = [
        _comparison_period(db, website_id, "huidige periode", current_start, period_end),
        _comparison_period(
            db,
            website_id,
            "vorige gelijkwaardige periode",
            previous_end - timedelta(days=days - 1),
            previous_end,
        ),
        _comparison_period(
            db,
            website_id,
            "dezelfde periode één jaar eerder",
            previous_year_end - timedelta(days=days - 1),
            previous_year_end,
        ),
        _comparison_period(
            db,
            website_id,
            "dezelfde periode twee jaar eerder",
            two_years_ago_end - timedelta(days=days - 1),
            two_years_ago_end,
        ),
    ]
    current, previous = periods[:2]
    missing = [
        f"{period.label.capitalize()} is onbekend door ontbrekende volledige datadekking."
        for period in periods
        if not period.covered
    ]
    source = current.source or previous.source
    if source is None:
        missing.insert(0, "Er is geen primaire analyticsbron voor deze website ingesteld.")
    elif not current.configured:
        missing.insert(0, "Gekwalificeerde lead-events zijn niet ingesteld voor deze bron.")
    quality_anomalies = current.anomalies + previous.anomalies
    if quality_anomalies:
        missing.insert(
            0,
            "De leadmeting bevat een sterke event-/sessieafwijking; herstel of verifieer eerst "
            "de tracking.",
        )
    facts = [_period_fact(period) for period in periods]
    interpretations: list[str] = []
    if current.covered and previous.covered:
        if quality_anomalies:
            interpretations.extend(_quality_interpretations(db, quality_anomalies))
            answer = _quality_limited_answer(current, previous, source)
        else:
            interpretations.extend(_comparison_interpretations(db, current, previous))
            answer = _performance_answer(current, previous, source)
    else:
        answer = (
            "De leadontwikkeling kan niet betrouwbaar worden vergeleken, omdat de huidige of "
            "direct voorafgaande gelijkwaardige periode geen volledige dekking heeft."
        )
    covered_count = sum(period.covered for period in periods)
    confidence = (
        "low"
        if quality_anomalies
        else "high"
        if covered_count >= 3
        else "medium"
        if covered_count >= 2
        else "low"
    )
    return {
        "status": ("answered" if current.covered and previous.covered else "insufficient_evidence"),
        "answer": answer,
        "facts": facts,
        "interpretations": interpretations,
        "missing_evidence": missing,
        "confidence": confidence,
        "sources": [
            {
                "source_type": f"analytics_{source or 'unknown'}",
                "record_id": website.id,
                "measured_at": None,
                "description": (
                    f"Primaire analyticsbron; vergelijking van {current_start.isoformat()} "
                    f"tot {period_end.isoformat()} met gelijkwaardige perioden"
                ),
            }
        ],
        "mutations_performed": False,
    }


def _comparison_period(
    db: Session, website_id: UUID, label: str, period_start: date, period_end: date
) -> ComparisonPeriod:
    totals = quality_aware_analytics_totals(db, website_id, period_start, period_end)
    source, rows = totals.source, totals.rows
    minimum, maximum = _analytics_date_bounds(db, website_id, source)
    return ComparisonPeriod(
        label=label,
        start=period_start,
        end=period_end,
        source=source,
        rows=rows,
        covered=bool(
            totals.configured
            and rows
            and minimum
            and maximum
            and minimum <= period_start
            and maximum >= period_end
        ),
        configured=totals.configured,
        anomalies=totals.anomalies,
    )


def _analytics_date_bounds(
    db: Session, website_id: UUID, source: str | None
) -> tuple[date | None, date | None]:
    model = (
        GoogleAnalyticsMetric
        if source == "ga4"
        else MatomoPageMetric
        if source == "matomo"
        else None
    )
    if model is None:
        return None, None
    return db.execute(
        select(func.min(model.date), func.max(model.date)).where(model.website_id == website_id)
    ).one()


def _period_fact(period: ComparisonPeriod) -> str:
    if not period.covered:
        return f"{period.label.capitalize()} ({period.start} t/m {period.end}): onbekend."
    visits = sum(row.visits for row in period.rows)
    conversions = sum(row.conversions for row in period.rows)
    rate = conversions / visits * 100 if visits else 0
    fact = (
        f"{period.label.capitalize()} ({period.start} t/m {period.end}): {visits} organische "
        f"sessies/bezoeken, {conversions:.1f} leads, conversieratio {rate:.2f}%."
    )
    if period.suspicious_conversions:
        adjusted = max(0.0, conversions - period.suspicious_conversions)
        adjusted_rate = adjusted / visits * 100 if visits else 0
        fact += (
            f" Zonder de verdachte bijdrage: {adjusted:.1f} leads en "
            f"{adjusted_rate:.2f}% conversieratio."
        )
    return fact


def _comparison_interpretations(
    db: Session, current: ComparisonPeriod, previous: ComparisonPeriod
) -> list[str]:
    current_totals = _totals(current.rows)
    previous_totals = _totals(previous.rows)
    conversion_delta = current_totals[1] - previous_totals[1]
    direction = (
        "toegenomen"
        if conversion_delta > 0
        else "afgenomen"
        if conversion_delta < 0
        else "gelijk gebleven"
    )
    result = [
        f"Leads zijn {direction} met {abs(conversion_delta):.1f} ten opzichte van de vorige "
        "gelijkwaardige periode."
    ]
    urls = {
        url.id: url.normalized_url
        for url in db.scalars(
            select(Url).where(Url.id.in_({row.url_id for row in current.rows + previous.rows}))
        )
    }
    current_by_url = {row.url_id: row for row in current.rows}
    previous_by_url = {row.url_id: row for row in previous.rows}
    drivers = []
    for url_id in set(current_by_url) | set(previous_by_url):
        current_row = current_by_url.get(url_id, AnalyticsPageTotal(url_id, 0, 0, 0))
        previous_row = previous_by_url.get(url_id, AnalyticsPageTotal(url_id, 0, 0, 0))
        delta = current_row.conversions - previous_row.conversions
        if delta:
            drivers.append((abs(delta), delta, url_id, current_row, previous_row))
    ranked_drivers = sorted(drivers, key=lambda item: (item[0], item[1]), reverse=True)
    for _magnitude, delta, url_id, current_row, previous_row in ranked_drivers[:5]:
        result.append(
            _driver_interpretation(urls.get(url_id, str(url_id)), delta, current_row, previous_row)
        )
    result.append(
        "Dit is geobserveerde samenhang. Zonder aanvullend bewijs wordt geen wijziging als "
        "oorzaak aangewezen."
    )
    return result


def _driver_interpretation(
    url: str,
    conversion_delta: float,
    current: AnalyticsPageTotal,
    previous: AnalyticsPageTotal,
) -> str:
    previous_rate = previous.conversions / previous.visits if previous.visits else 0
    current_rate = current.conversions / current.visits if current.visits else 0
    traffic_effect = (current.visits - previous.visits) * previous_rate
    rate_effect = current.visits * (current_rate - previous_rate)
    driver = "verkeer" if abs(traffic_effect) >= abs(rate_effect) else "conversieratio"
    return (
        f"{url}: {conversion_delta:+.1f} leads; grootste rekenkundige bijdrage komt van {driver} "
        f"({previous.visits}→{current.visits} bezoeken; {previous_rate * 100:.2f}%→"
        f"{current_rate * 100:.2f}%)."
    )


def _totals(rows: list[AnalyticsPageTotal]) -> tuple[int, float]:
    return sum(row.visits for row in rows), sum(row.conversions for row in rows)


def _performance_answer(
    current: ComparisonPeriod, previous: ComparisonPeriod, source: str | None
) -> str:
    current_visits, current_conversions = _totals(current.rows)
    previous_visits, previous_conversions = _totals(previous.rows)
    return (
        f"Volgens de primaire bron {(source or 'onbekend').upper()} veranderden organische leads "
        f"van {previous_conversions:.1f} naar {current_conversions:.1f} en bezoeken van "
        f"{previous_visits} naar {current_visits}. De pagina-aandrijvers hieronder splitsen de "
        "rekenkundige bijdrage van verkeer en conversieratio; dit bewijst geen causaliteit."
    )


def _quality_limited_answer(
    current: ComparisonPeriod, previous: ComparisonPeriod, source: str | None
) -> str:
    _current_visits, current_raw = _totals(current.rows)
    _previous_visits, previous_raw = _totals(previous.rows)
    current_adjusted = max(0.0, current_raw - current.suspicious_conversions)
    previous_adjusted = max(0.0, previous_raw - previous.suspicious_conversions)
    return (
        f"De primaire bron {(source or 'onbekend').upper()} toont ruwe leads van "
        f"{previous_raw:.1f} naar {current_raw:.1f}; zonder verdachte bijdragen is dit "
        f"{previous_adjusted:.1f} naar {current_adjusted:.1f}. Door de meetafwijking wordt nog "
        "geen leadconclusie of pagina-advies gegeven. Controleer eerst de tracking."
    )


def _quality_interpretations(db: Session, anomalies: list[AnalyticsAnomaly]) -> list[str]:
    urls = {
        url.id: url.normalized_url
        for url in db.scalars(select(Url).where(Url.id.in_({item.url_id for item in anomalies})))
    }
    result = []
    for item in anomalies[:5]:
        result.append(
            f"Mogelijke meetafwijking op {urls.get(item.url_id, str(item.url_id))}: "
            f"{item.events:.1f} events bij {item.sessions} sessies op {item.date.isoformat()} "
            f"voor event {item.event_name}."
        )
    result.append(
        "De verdachte events zijn niet verwijderd; alleen de gevoeligheidsberekening sluit hun "
        "bijdrage tijdelijk uit."
    )
    return result


def _shift_year(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)


def _scope_limited_answer() -> dict[str, object]:
    return {
        "status": "scope_limited",
        "answer": (
            "Ik beantwoord alleen vragen over het zichtbare klantrecord en de betekenis daarvan "
            "binnen SEO Monitor. Marktvergelijkingen, concurrenten en externe tools vallen buiten "
            "deze assistent."
        ),
        "facts": [],
        "interpretations": [],
        "missing_evidence": ["De gevraagde informatie behoort niet tot de zichtbare klantcontext."],
        "confidence": "not_applicable",
        "sources": [],
        "mutations_performed": False,
    }

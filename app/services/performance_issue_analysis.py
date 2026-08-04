import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crawl import UrlSnapshot
from app.models.issues import Issue
from app.models.performance import PerformanceObservation
from app.services.issue_engine import reconcile_issues
from app.services.technical_checks import IssueSignal


@dataclass(frozen=True)
class PerformanceRule:
    issue_type: str
    audit_ids: frozenset[str]
    title: str
    description: str
    action: str


PERFORMANCE_RULES = (
    PerformanceRule(
        "lighthouse_image_delivery",
        frozenset(
            {
                "modern-image-formats",
                "offscreen-images",
                "uses-optimized-images",
                "uses-responsive-images",
            }
        ),
        "Afbeeldingen veroorzaken aantoonbare laadvertraging",
        "Lighthouse heeft concrete afbeeldingen gevonden die onnodig groot, vroeg geladen of "
        "ongeschikt geschaald zijn.",
        "Optimaliseer de genoemde afbeeldingen en controleer formaat, afmetingen, responsive "
        "bronnen en lazy loading in het gedeelde template of component.",
    ),
    PerformanceRule(
        "lighthouse_unused_javascript",
        frozenset({"unused-javascript"}),
        "Ongebruikte JavaScript-belasting verminderen",
        "Lighthouse heeft JavaScript-bestanden met aantoonbaar ongebruikte overdracht gevonden.",
        "Laad de genoemde scripts alleen waar nodig, splits bundels of verwijder ongebruikte code "
        "en controleer daarna dezelfde pagina's opnieuw.",
    ),
    PerformanceRule(
        "lighthouse_unused_css",
        frozenset({"unused-css-rules"}),
        "Ongebruikte CSS-belasting verminderen",
        "Lighthouse heeft stylesheets met aantoonbaar ongebruikte overdracht gevonden.",
        "Beperk de genoemde stylesheets tot noodzakelijke regels, splits kritieke en overige CSS "
        "en controleer visuele regressies.",
    ),
    PerformanceRule(
        "lighthouse_render_blocking_resources",
        frozenset({"render-blocking-resources", "render-blocking-insight"}),
        "Render-blocking resources verkorten",
        "Concrete CSS- of JavaScript-resources vertragen volgens Lighthouse de eerste weergave.",
        "Bepaal per genoemde resource of inline critical CSS, uitgesteld laden of een kleinere "
        "bundel passend is en controleer de laadvolgorde opnieuw.",
    ),
    PerformanceRule(
        "lighthouse_cache_policy",
        frozenset({"uses-long-cache-ttl", "cache-insight"}),
        "Caching voor statische resources verbeteren",
        "Lighthouse heeft resources met een aantoonbaar korte of ontbrekende cacheduur gevonden.",
        "Stel voor versieerbare statische bestanden een passende lange cacheduur in en voorkom "
        "lange caching voor niet-geversioneerde dynamische inhoud.",
    ),
    PerformanceRule(
        "lighthouse_font_and_third_party_delivery",
        frozenset({"font-display", "font-display-insight", "third-party-summary"}),
        "Fonts en externe scripts doelgerichter laden",
        "Lighthouse wijst concrete font- of externe resources aan die de laadervaring belasten.",
        "Beperk externe scripts tot noodzakelijke pagina's en optimaliseer fontselectie, preload "
        "en font-display zonder inhoud of functionaliteit te verbergen.",
    ),
    PerformanceRule(
        "lighthouse_lcp_delivery",
        frozenset(
            {
                "largest-contentful-paint-element",
                "lcp-breakdown-insight",
                "lcp-discovery-insight",
                "server-response-time",
            }
        ),
        "LCP-resource of serverreactie verbeteren",
        "Lighthouse bevat concrete oorzaakinformatie voor het grootste zichtbare element of de "
        "serverreactietijd.",
        "Optimaliseer eerst de genoemde LCP-resource, ontdekkingsroute of serverfase en herhaal "
        "daarna dezelfde mobiele of desktopmeting.",
    ),
)
PERFORMANCE_ISSUE_TYPES = {rule.issue_type for rule in PERFORMANCE_RULES}


def analyze_performance_observation(
    db: Session, observation: PerformanceObservation
) -> list[Issue]:
    if observation.status != "succeeded":
        return []
    snapshot = db.scalar(
        select(UrlSnapshot)
        .where(UrlSnapshot.url_id == observation.url_id)
        .order_by(UrlSnapshot.checked_at.desc())
        .limit(1)
    )
    if snapshot is None:
        return []
    failed = [audit for audit in observation.failed_audits if isinstance(audit, dict)]
    signals = [
        signal
        for rule in PERFORMANCE_RULES
        if (signal := _signal(rule, observation, failed))
    ]
    issues = reconcile_issues(
        db,
        website_id=observation.website_id,
        url_id=observation.url_id,
        crawl_run_id=snapshot.crawl_run_id,
        snapshot_id=snapshot.id,
        signals=signals,
        checked_issue_types=PERFORMANCE_ISSUE_TYPES,
    )
    db.flush()
    return issues


def _signal(
    rule: PerformanceRule,
    observation: PerformanceObservation,
    failed: list[dict[str, object]],
) -> IssueSignal | None:
    matching = [audit for audit in failed if audit.get("audit_id") in rule.audit_ids]
    if not matching:
        return None
    resources = sorted(
        {
            str(item["url"])
            for audit in matching
            for item in audit.get("items", [])
            if isinstance(item, dict) and isinstance(item.get("url"), str)
        }
    )
    wasted_bytes = sum(_numeric_item(audit, "wastedBytes") for audit in matching)
    wasted_ms = sum(
        max(
            _number(audit.get("numeric_value")),
            _numeric_item(audit, "wastedMs"),
        )
        for audit in matching
    )
    audit_ids = sorted(str(audit["audit_id"]) for audit in matching)
    cause_material = {"issue_type": rule.issue_type, "audits": audit_ids, "resources": resources}
    return IssueSignal(
        issue_type=rule.issue_type,
        category="performance",
        severity="medium" if wasted_bytes >= 250_000 or wasted_ms >= 1_000 else "low",
        confidence="medium",
        title=rule.title,
        description=rule.description,
        recommended_action=rule.action,
        evidence={
            "source": "pagespeed_insights",
            "performance_observation_id": str(observation.id),
            "strategy": observation.strategy,
            "lighthouse_version": observation.lighthouse_version,
            "audit_ids": audit_ids,
            "audits": matching,
            "resources": resources,
            "wasted_bytes": wasted_bytes,
            "potential_savings_ms": round(wasted_ms, 1),
            "category_scores": observation.category_scores,
            "field_metrics": observation.field_metrics,
            "cause_key": hashlib.sha256(
                json.dumps(cause_material, sort_keys=True).encode()
            ).hexdigest()[:16],
        },
    )


def _numeric_item(audit: dict[str, object], key: str) -> float:
    items = audit.get("items", [])
    if not isinstance(items, list):
        return 0
    return sum(_number(item.get(key)) for item in items if isinstance(item, dict))


def _number(value: object) -> float:
    return float(value) if isinstance(value, int | float) else 0

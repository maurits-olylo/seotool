from app.models.discovery import Url
from app.models.issues import Issue

CATEGORY_DOMAIN_LABELS = {
    "accessibility": "toegankelijkheid",
    "content": "content",
    "indexability": "vindbaarheid",
    "internal_links": "sitestructuur",
    "onpage": "SEO",
    "performance": "performance",
    "reachability": "techniek",
    "rendering": "rendering",
    "structured_data": "structured data",
}
SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def priority_factors(
    *,
    url: Url,
    issues: list[Issue],
    reach: int,
    feasibility: str,
    has_search_evidence: bool,
    impressions: int,
    additional_domains: set[str] | None = None,
) -> list[dict[str, object]]:
    domains = sorted(
        {
            CATEGORY_DOMAIN_LABELS.get(issue.category, issue.category.replace("_", " "))
            for issue in issues
        }
        | {"SEO"}
        | (additional_domains or set())
    )
    strongest = max(
        (issue.severity for issue in issues),
        key=lambda value: SEVERITY_RANK.get(value, 0),
        default="low",
    )
    missing = [] if has_search_evidence else ["zoekprestatie"]
    summary_parts = [f"impact op {' en '.join(domains)}"]
    if reach > 1:
        summary_parts.append(f"gedeelde oorzaak op {reach} pagina's")
    elif url.is_important:
        summary_parts.append("belangrijke pagina")
    if feasibility == "direct":
        summary_parts.append("direct uitvoerbaar")
    summary = "; ".join(summary_parts)
    summary = summary[:1].upper() + summary[1:] + "."
    return [
        {
            "dimension": "explanation",
            "signal": "priority_summary",
            "label": "Waarom nu",
            "value": summary,
            "direction": "context",
        },
        {
            "dimension": "impact",
            "signal": "impact_domains",
            "label": "Impactdomeinen",
            "value": domains,
            "direction": "context",
        },
        {
            "dimension": "reach",
            "signal": "affected_pages",
            "label": "Bereik",
            "value": reach,
            "direction": "positive" if reach > 1 else "context",
        },
        {
            "dimension": "confidence",
            "signal": "evidence_completeness",
            "label": "Bewijs",
            "value": "compleet" if not missing else "aanvullende observatie wenselijk",
            "missing_sources": missing,
            "direction": "positive" if not missing else "context",
        },
        {
            "dimension": "effort",
            "signal": "feasibility",
            "label": "Uitvoerbaarheid",
            "value": feasibility,
            "direction": "context",
        },
        {
            "dimension": "urgency",
            "signal": "strongest_issue_severity",
            "label": "Urgentie",
            "value": strongest,
            "direction": "negative",
        },
        {
            "dimension": "business_context",
            "signal": "important_page_context",
            "label": "Businesscontext",
            "value": {
                "important_url": bool(url.is_important),
                "observed_demand": impressions,
            },
            "direction": "positive" if url.is_important or impressions else "context",
        },
    ]

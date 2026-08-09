import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.discovery import Url
from app.models.integrations import SearchConsoleMetric
from app.models.issues import Issue
from app.models.opportunities import OpportunityEvaluation
from app.models.website import Website
from app.services.opportunity_engine import evaluate_website_opportunities

PERIOD_START = date(2026, 7, 1)
PERIOD_END = PERIOD_START + timedelta(days=27)
ACCESSIBILITY_URL = "https://release-12-priority.invalid/important-contact"
SEO_URL = "https://release-12-priority.invalid/service"


def _get_or_create_url(db, website_id, value: str, *, important: bool) -> Url:
    url = db.scalar(
        select(Url).where(Url.website_id == website_id, Url.normalized_url == value)
    )
    if url is None:
        url = Url(website_id=website_id, normalized_url=value)
        db.add(url)
        db.flush()
    url.current_status_code = 200
    url.current_final_url = value
    url.is_active = True
    url.is_indexable = True
    url.is_important = important
    url.page_type = "staging_acceptance"
    url.crawl_depth = 2
    return url


def _get_or_create_issue(
    db,
    url: Url,
    *,
    issue_type: str,
    category: str,
    severity: str,
) -> Issue:
    issue = db.scalar(
        select(Issue).where(
            Issue.website_id == url.website_id,
            Issue.url_id == url.id,
            Issue.issue_type == issue_type,
        )
    )
    if issue is None:
        issue = Issue(
            website_id=url.website_id,
            url_id=url.id,
            issue_type=issue_type,
            category=category,
            severity=severity,
            confidence="high",
            title=f"Synthetisch {category}signaal",
            description="Klantvrije acceptatiefixture voor uitlegbare prioritering.",
            recommended_action="Controleer en herstel het aantoonbare signaal.",
        )
        db.add(issue)
    issue.category = category
    issue.severity = severity
    issue.confidence = "high"
    issue.status = "new"
    issue.resolved_at = None
    issue.verified_at = None
    return issue


def _prepare_search_metrics(db, url: Url) -> None:
    for offset in range(28):
        day = PERIOD_START + timedelta(days=offset)
        metric = db.scalar(
            select(SearchConsoleMetric).where(
                SearchConsoleMetric.website_id == url.website_id,
                SearchConsoleMetric.url_id == url.id,
                SearchConsoleMetric.date == day,
            )
        )
        if metric is None:
            metric = SearchConsoleMetric(
                website_id=url.website_id,
                url_id=url.id,
                date=day,
                page_url=url.normalized_url,
            )
            db.add(metric)
        metric.clicks = 0.2
        metric.impressions = 20
        metric.ctr = 0.01
        metric.position = 7


def _factor(evaluation: OpportunityEvaluation, signal: str) -> dict[str, object]:
    return next(item for item in evaluation.contributors if item.get("signal") == signal)


def _assert_user_interface() -> None:
    source = (Path(__file__).resolve().parents[1] / "app/ui/app.js").read_text()
    required = (
        'gsc: "Zoekprestatie"',
        'crawler_issues: "Paginacontrole"',
        "Waarom deze prioriteit?",
    )
    if not all(value in source for value in required):
        raise RuntimeError("Factor-oriented opportunity interface is incomplete")
    if "opportunityScoreMarkup" in source or "${total}/100" in source:
        raise RuntimeError("Universal opportunity score is still visible")


def main() -> None:
    _assert_user_interface()
    with SessionLocal() as db:
        website = db.scalar(
            select(Website).where(Website.name.like("[STAGING]%")).order_by(Website.created_at)
        )
        if website is None:
            raise RuntimeError("No synthetic staging website exists")
        accessibility_url = _get_or_create_url(
            db, website.id, ACCESSIBILITY_URL, important=True
        )
        seo_url = _get_or_create_url(db, website.id, SEO_URL, important=False)
        _get_or_create_issue(
            db,
            accessibility_url,
            issue_type="accessibility_label",
            category="accessibility",
            severity="high",
        )
        _get_or_create_issue(
            db,
            seo_url,
            issue_type="missing_meta_description",
            category="onpage",
            severity="medium",
        )
        _prepare_search_metrics(db, seo_url)
        db.commit()

        evaluate_website_opportunities(db, website.id, PERIOD_START, PERIOD_END)
        accessibility = db.scalar(
            select(OpportunityEvaluation)
            .where(
                OpportunityEvaluation.website_id == website.id,
                OpportunityEvaluation.scope_key
                == f"important_accessibility:{accessibility_url.id}",
            )
            .order_by(OpportunityEvaluation.created_at.desc())
        )
        seo = db.scalar(
            select(OpportunityEvaluation)
            .where(
                OpportunityEvaluation.website_id == website.id,
                OpportunityEvaluation.scope_key == f"ctr:{seo_url.id}",
            )
            .order_by(OpportunityEvaluation.created_at.desc())
        )
        if accessibility is None or seo is None:
            raise RuntimeError("Expected cross-domain and SEO opportunities")
        if accessibility.source_coverage.get("gsc") is not False:
            raise RuntimeError("Accessibility candidate unexpectedly requires search data")
        domains = _factor(accessibility, "impact_domains")["value"]
        if domains != ["SEO", "toegankelijkheid"]:
            raise RuntimeError(f"Unexpected cross-domain impact: {domains}")
        missing = _factor(accessibility, "evidence_completeness").get("missing_sources")
        if missing != ["zoekprestatie"]:
            raise RuntimeError(f"Missing evidence is not explicit: {missing}")
        if _factor(seo, "impact_domains")["value"] != ["SEO"]:
            raise RuntimeError("Existing SEO opportunity does not use factor-oriented priority")
        if _factor(seo, "feasibility")["value"] != "direct":
            raise RuntimeError("SEO feasibility explanation is missing")
        print(
            {
                "status": "release_12_phase_d_staging_ok",
                "cross_domain_opportunity_id": str(accessibility.id),
                "seo_opportunity_id": str(seo.id),
                "searchless_candidate": True,
                "factor_oriented_ui": True,
            }
        )


if __name__ == "__main__":
    main()

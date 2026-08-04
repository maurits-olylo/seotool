from datetime import UTC, datetime

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.issues import Issue, IssueOccurrence
from app.models.performance import PerformanceObservation
from app.models.website import Website, WebsiteSettings
from app.services.issue_classification import issue_nature, issue_scope
from app.services.performance_issue_analysis import analyze_performance_observation
from app.services.recommendation_library import recommendation_for_issue_type
from app.services.template_issue_analysis import analyze_template_issue_clusters


def test_failed_audits_create_evidence_bound_performance_actions() -> None:
    with SessionLocal() as db:
        website, run, urls = _crawl_with_urls(db, 1)
        observation = _observation(
            db,
            website.id,
            urls[0].id,
            failed_audits=[
                {
                    "audit_id": "unused-javascript",
                    "score": 0.3,
                    "numeric_value": 1300,
                    "items": [
                        {
                            "url": "https://cdn.example.com/app.js",
                            "wastedBytes": 300000,
                        }
                    ],
                },
                {
                    "audit_id": "uses-responsive-images",
                    "score": 0.6,
                    "items": [{"url": "https://example.com/hero.jpg", "wastedBytes": 80000}],
                },
            ],
        )

        issues = analyze_performance_observation(db, observation)
        db.commit()

        assert {issue.issue_type for issue in issues} == {
            "lighthouse_image_delivery",
            "lighthouse_unused_javascript",
        }
        javascript = next(
            issue for issue in issues if issue.issue_type == "lighthouse_unused_javascript"
        )
        occurrence = db.scalar(
            select(IssueOccurrence).where(IssueOccurrence.issue_id == javascript.id)
        )
        assert javascript.severity == "medium"
        assert occurrence is not None
        assert occurrence.crawl_run_id == run.id
        assert occurrence.evidence["audit_ids"] == ["unused-javascript"]
        assert occurrence.evidence["resources"] == ["https://cdn.example.com/app.js"]
        assert issue_scope(javascript.issue_type) == "performance"
        assert issue_nature(javascript.issue_type) == "optimization"
        assert (
            recommendation_for_issue_type(javascript.issue_type).key
            == "improve_measured_page_performance"
        )


def test_scores_without_failed_audits_do_not_create_actions() -> None:
    with SessionLocal() as db:
        website, _run, urls = _crawl_with_urls(db, 1)
        observation = _observation(
            db,
            website.id,
            urls[0].id,
            category_scores={"performance": 0.2},
            failed_audits=[],
        )

        assert analyze_performance_observation(db, observation) == []
        db.commit()
        assert db.query(Issue).count() == 0


def test_clean_remeasure_resolves_then_verifies_existing_action() -> None:
    with SessionLocal() as db:
        website, _run, urls = _crawl_with_urls(db, 1)
        failing = _observation(
            db,
            website.id,
            urls[0].id,
            failed_audits=[{"audit_id": "unused-css-rules", "score": 0.4, "items": []}],
        )
        analyze_performance_observation(db, failing)
        db.commit()

        clean = _observation(db, website.id, urls[0].id, failed_audits=[])
        analyze_performance_observation(db, clean)
        db.commit()
        issue = db.scalar(select(Issue).where(Issue.issue_type == "lighthouse_unused_css"))
        assert issue is not None and issue.status == "resolved"

        verified = _observation(db, website.id, urls[0].id, failed_audits=[])
        analyze_performance_observation(db, verified)
        db.commit()
        db.refresh(issue)
        assert issue.status == "verified"


def test_shared_resource_is_grouped_as_one_template_action() -> None:
    with SessionLocal() as db:
        website, run, urls = _crawl_with_urls(db, 2)
        for url in urls:
            observation = _observation(
                db,
                website.id,
                url.id,
                failed_audits=[
                    {
                        "audit_id": "unused-javascript",
                        "score": 0.4,
                        "items": [{"url": "https://cdn.example.com/shared.js"}],
                    }
                ],
            )
            analyze_performance_observation(db, observation)
        db.commit()

        clusters = analyze_template_issue_clusters(
            db, website_id=website.id, crawl_run_id=run.id
        )
        db.commit()

        assert [issue.issue_type for issue in clusters] == [
            "lighthouse_unused_javascript_clusters"
        ]
        assert clusters[0].category == "performance"


def _crawl_with_urls(db, count):  # type: ignore[no-untyped-def]
    website = Website(
        client=Client(name=f"Performance issue client {count}"),
        name=f"Performance issue site {count}",
        base_url="https://example.com/",
    )
    website.settings = WebsiteSettings()
    db.add(website)
    db.flush()
    job = CrawlJob(
        website_id=website.id, job_type="full_site_crawl", status="succeeded"
    )
    db.add(job)
    db.flush()
    run = CrawlRun(
        crawl_job_id=job.id,
        website_id=website.id,
        crawl_type="full_site_crawl",
        status="succeeded",
    )
    db.add(run)
    db.flush()
    urls = []
    for index in range(count):
        url = Url(
            website_id=website.id,
            normalized_url=f"https://example.com/products/{index}",
            is_active=True,
            current_status_code=200,
            is_indexable=True,
        )
        db.add(url)
        db.flush()
        db.add(
            UrlSnapshot(
                url_id=url.id,
                crawl_run_id=run.id,
                requested_url=url.normalized_url,
                final_url=url.normalized_url,
                status_code=200,
                content_type="text/html",
                redirect_chain=[],
            )
        )
        urls.append(url)
    db.commit()
    return website, run, urls


def _observation(
    db,
    website_id,
    url_id,
    *,
    failed_audits,
    category_scores=None,
):  # type: ignore[no-untyped-def]
    observation = PerformanceObservation(
        website_id=website_id,
        url_id=url_id,
        analyzed_at=datetime.now(UTC),
        strategy="mobile",
        status="succeeded",
        requested_url="https://example.com/page",
        lighthouse_version="13.0.0",
        category_scores=category_scores or {"performance": 0.7},
        failed_audits=failed_audits,
    )
    db.add(observation)
    db.flush()
    return observation

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select

from app.db.session import SessionLocal, engine
from app.models.client import Client
from app.models.common import utc_now
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.issues import Issue, IssueOccurrence
from app.models.recommendations import RecommendationTask
from app.models.website import Website
from app.services.work_preview import assess


def issue(kind="sitemap_404", status="new", confidence="high"):
    return Issue(
        id=uuid4(),
        issue_type=kind,
        status=status,
        confidence=confidence,
        severity="low" if kind == "possibly_outdated_content" else "high",
        title="Voorbeeld",
        description="Bewijs",
        recommended_action="Actie",
    )


@pytest.mark.parametrize(
    "kind,status,fresh,expected",
    [
        ("sitemap_404", "new", True, "decision"),
        ("expired_job_posting_404", "new", True, "decision"),
        ("duplicate_meta_description", "new", True, "decision"),
        ("orphan_page", "new", True, "research"),
        ("structured_data_visible_content_mismatch", "new", True, "research"),
        ("possibly_outdated_content", "new", False, "periodic"),
        ("unknown_future_type", "new", True, "unassessed"),
        ("sitemap_404", "verified", False, "history"),
        ("sitemap_404", "resolved", True, "research"),
        ("sitemap_404", "new", False, "research"),
        ("sitemap_404", "review", True, "research"),
        ("internally_linked_redirect", "new", True, "research"),
    ],
)
def test_conservative_routes(kind, status, fresh, expected):
    result = assess(
        issue(kind, status), current_evidence=fresh, partial=False, tasks=[], now=utc_now()
    )
    assert result["lane"] == expected
    assert result["first_step"] and result["completion"] and result["role"]


def test_existing_work_requires_approval_current_version_and_no_blockers():
    sample = issue("internally_linked_redirect", "accepted")
    task = RecommendationTask(
        id=uuid4(),
        status="planned",
        feasibility="direct",
        assigned_to_user_id=uuid4(),
        dependencies=[],
        required_input=[],
        steps=["Vervang de afgesproken link"],
        acceptance_criteria=["Controleer de bestemming"],
        definition_version="2",
        recommendation_type="replace_redirected_internal_link",
        primary_role="content",
    )

    def route(partial=False):
        return assess(sample, current_evidence=True, partial=partial, tasks=[task], now=utc_now())[
            "lane"
        ]

    assert route() == "execute"
    assert route(True) == "research"
    task.dependencies = ["Wacht op besluit"]
    assert route() == "research"
    task.dependencies = []
    task.definition_version = "1"
    assert route() == "research"
    task.definition_version = "2"
    sample.status = "new"
    assert route() == "research"


def test_due_redactional_review_is_not_hidden_as_periodic():
    sample = issue("possibly_outdated_content")
    sample.due_date = utc_now().date()
    assert (
        assess(sample, current_evidence=False, partial=False, tasks=[], now=utc_now())["lane"]
        == "research"
    )


def setup_site():
    with SessionLocal() as db:
        site = Website(client=Client(name="Pilot"), name="HUMAN", base_url="https://www.human.nl")
        db.add(site)
        db.flush()
        url = Url(website_id=site.id, normalized_url="https://www.human.nl/page")
        job = CrawlJob(website_id=site.id, job_type="full_site_crawl", status="succeeded")
        db.add_all([url, job])
        db.flush()
        run = CrawlRun(
            website_id=site.id,
            crawl_job_id=job.id,
            crawl_type="full_site_crawl",
            status="succeeded",
        )
        db.add(run)
        db.flush()
        snapshot = UrlSnapshot(url_id=url.id, crawl_run_id=run.id, requested_url=url.normalized_url)
        db.add(snapshot)
        db.flush()
        record = issue()
        record.website_id, record.url_id, record.category = site.id, url.id, "technical"
        db.add(record)
        db.flush()
        db.add(IssueOccurrence(issue_id=record.id, crawl_run_id=run.id, snapshot_id=snapshot.id))
        db.commit()
        return site.id, url.id, run.id


def test_api_read_only_pagination_and_newer_snapshot(client):
    site, url, run = setup_site()
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().split()[0].upper())

    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.get(f"/api/v1/websites/{site}/work-preview?lane=decision&limit=1")
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert response.status_code == 200
    assert response.json()["counts"]["decision"] == 1
    assert len(response.json()["items"]) == 1
    assert not set(statements) & {"INSERT", "UPDATE", "DELETE"}
    with SessionLocal() as db:
        db.add(
            UrlSnapshot(
                url_id=url,
                crawl_run_id=run,
                requested_url="https://www.human.nl/page",
                checked_at=utc_now() + timedelta(seconds=1),
            )
        )
        db.commit()
        assert db.scalar(select(func.count()).select_from(RecommendationTask)) == 0
    data = client.get(f"/api/v1/websites/{site}/work-preview").json()
    assert data["counts"]["research"] == 1
    assert data["items"][0]["current_evidence"] is False
    assert client.get(f"/api/v1/websites/{site}/work-preview?lane=bad").status_code == 422
    assert client.get(f"/api/v1/websites/{site}/work-preview?limit=5000").status_code == 422


def test_other_tenant_denied(client):
    from app.core.security import Principal, require_api_key
    from app.main import app

    site, _, _ = setup_site()
    app.dependency_overrides[require_api_key] = lambda: Principal(
        user_id=uuid4(), role="admin", is_api_key=False
    )
    try:
        assert client.get(f"/api/v1/websites/{site}/work-preview").status_code == 403
    finally:
        app.dependency_overrides.pop(require_api_key)


def test_preview_page_requires_login(client):
    assert client.get("/app/work-preview", follow_redirects=False).status_code == 302


def test_search_pagination_keep_distribution_counts(client):
    site, _, _ = setup_site()
    root = f"/api/v1/websites/{site}/work-preview"
    data = client.get(root, params={"q": "missing-match"}).json()
    assert data["total"] == 0 and data["items"] == []
    assert sum(data["counts"].values()) == 1
    data = client.get(root, params={"q": "VOORBEELD"}).json()
    assert data["total"] == 1
    assert client.get(root, params={"offset": 1}).json()["items"] == []


def test_high_severity_age_finding_requires_review():
    sample = issue("possibly_outdated_content")
    sample.severity = "high"
    result = assess(sample, current_evidence=True, partial=False, tasks=[], now=utc_now())
    assert result["lane"] == "research"

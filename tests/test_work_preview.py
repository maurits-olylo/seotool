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
        ("sitemap_404", "resolved", True, "verification"),
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
        snapshot = UrlSnapshot(
            url_id=url.id, crawl_run_id=run.id, requested_url=url.normalized_url, status_code=404
        )
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


def test_full_evidence_survives_light_check_but_not_changed_destination(client):
    site, url, run = setup_site()
    with SessionLocal() as db:
        record = db.scalar(select(Issue).where(Issue.website_id == site))
        record.issue_type = "duplicate_meta_description"
        snapshot = db.scalar(select(UrlSnapshot).where(UrlSnapshot.url_id == url))
        snapshot.metadata_hash = "full-analysis"
        snapshot.status_code = 200
        snapshot.final_url = "https://www.human.nl/page"
        occurrence = db.scalar(select(IssueOccurrence).where(IssueOccurrence.issue_id == record.id))
        occurrence.evidence = {
            "value": "Shared description",
            "related_urls": ["https://www.human.nl/other"],
        }
        light = UrlSnapshot(
            url_id=url,
            crawl_run_id=run,
            requested_url=snapshot.requested_url,
            final_url=snapshot.final_url,
            status_code=200,
            checked_at=utc_now() + timedelta(seconds=1),
        )
        db.add(light)
        db.commit()
        light_id = light.id
    endpoint = f"/api/v1/websites/{site}/work-preview"
    item = client.get(endpoint).json()["items"][0]
    assert item["lane"] == "decision"
    assert item["current_evidence"] is True
    assert "https://www.human.nl/other" in " ".join(item["evidence_facts"])
    assert "Shared description" in " ".join(item["evidence_facts"])
    assert "doelgroep" in item["first_step"]
    with SessionLocal() as db:
        db.get(UrlSnapshot, light_id).final_url = "https://www.human.nl/changed"
        db.commit()
    item = client.get(endpoint).json()["items"][0]
    assert item["lane"] == "research"
    assert item["evidence_code"] == "changed_reachability"


def test_history_and_verification_are_separate(client):
    site, _, _ = setup_site()
    with SessionLocal() as db:
        record = db.scalar(select(Issue).where(Issue.website_id == site))
        record.status = "verified"
        db.commit()
    endpoint = f"/api/v1/websites/{site}/work-preview"
    data = client.get(endpoint).json()
    assert data["items"] == [] and data["counts"]["history"] == 1
    assert client.get(endpoint, params={"lane": "history"}).json()["total"] == 1
    assert client.get(endpoint, params={"include_history": True}).json()["total"] == 1
    with SessionLocal() as db:
        record = db.scalar(select(Issue).where(Issue.website_id == site))
        record.status = "resolved"
        db.commit()
    assert client.get(endpoint).json()["items"][0]["lane"] == "verification"


@pytest.mark.parametrize("kind", ["orphan_page", "sitemap_404"])
def test_snapshotless_site_evidence_is_explained(client, kind):
    site, _, _ = setup_site()
    with SessionLocal() as db:
        record = db.scalar(select(Issue).where(Issue.website_id == site))
        record.issue_type, record.status = kind, "review"
        occurrence = db.scalar(select(IssueOccurrence).where(IssueOccurrence.issue_id == record.id))
        occurrence.snapshot_id = None
        db.commit()
    item = client.get(f"/api/v1/websites/{site}/work-preview").json()["items"][0]
    assert item["evidence_code"] == "site_evidence_needed"
    assert "ter beoordeling" in item["reason"]
    assert "homepagina" not in item["first_step"]  # UI consistently calls it homepage.
    assert ("homepage" if kind == "orphan_page" else "sitemap") in item["first_step"]


def test_schema_review_identifies_organization_and_no_blanket_route_warning():
    from app.services.work_preview_guidance import evidence_facts

    result = assess(
        issue("structured_data_visible_content_mismatch", confidence="low"),
        current_evidence=False,
        partial=True,
        tasks=[],
        now=utc_now(),
        evidence_reason="Oud bewijs",
    )
    assert "organisatienaam" in result["first_step"]
    assert "ontbrekende routes" not in result["reason"]
    facts = evidence_facts(
        "structured_data_visible_content_mismatch",
        {
            "mismatches": [
                {"schema_type": "Organization", "field": "name", "schema_value": "Voorbeeld"}
            ]
        },
    )
    assert "Organization" in facts[0] and "Voorbeeld" in facts[0]
    assert "huidige schemavergelijking" in facts[-1]


def test_query_review_uses_stored_period_and_existing_work_read_only(client):
    from app.models.integrations import SearchConsoleQueryMetric
    from app.models.recommendations import RecommendationTaskUrl

    site, url, _ = setup_site()
    with SessionLocal() as db:
        task = RecommendationTask(
            website_id=site,
            recommendation_type="content_question_gap",
            definition_version="1",
            title="Bestaand inhoudelijk werk",
            category="content",
            primary_role="content",
            priority_reason="Afgesproken",
            feasibility="review_required",
            action="Beoordeel",
            rationale="Zoekvraag",
        )
        db.add(task)
        db.flush()
        db.add(RecommendationTaskUrl(task_id=task.id, url_id=url, role="page"))
        for days, impressions in [(10, 80), (11, 20), (40, 999)]:
            db.add(
                SearchConsoleQueryMetric(
                    website_id=site,
                    url_id=url,
                    page_url="https://www.human.nl/page",
                    query="hoe los ik het probleem op",
                    date=utc_now().date() - timedelta(days=days),
                    impressions=impressions,
                    clicks=2,
                )
            )
        db.commit()
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().split()[0].upper())

    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.get(
            f"/api/v1/websites/{site}/work-preview", params={"lane": "opportunity"}
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert "actualiseer" in item["reason"]
    assert "100 vertoningen" in " ".join(item["evidence_facts"])
    assert "999" not in " ".join(item["evidence_facts"])
    assert "pas daarna" in item["first_step"]
    assert item["tasks"][0]["title"] == "Bestaand inhoudelijk werk"
    assert response.json()["total_opportunities"] == 1
    assert not set(statements) & {"INSERT", "UPDATE", "DELETE"}


def test_age_only_case_has_no_route_warning():
    result = assess(
        issue("possibly_outdated_content"),
        current_evidence=False,
        partial=True,
        tasks=[],
        now=utc_now(),
    )
    assert result["lane"] == "periodic"
    assert result["role"] == "Eindredacteur"
    assert "archieffunctie" in result["first_step"]
    assert "routes" not in result["reason"]


def test_old_analysis_cannot_be_refreshed_by_occurrence_timestamp(client):
    site, url, _ = setup_site()
    with SessionLocal() as db:
        record = db.scalar(select(Issue).where(Issue.website_id == site))
        record.issue_type = "duplicate_meta_description"
        snapshot = db.scalar(select(UrlSnapshot).where(UrlSnapshot.url_id == url))
        snapshot.metadata_hash = "analyzed"
        snapshot.checked_at = utc_now() - timedelta(days=8)
        db.commit()
    item = client.get(f"/api/v1/websites/{site}/work-preview").json()["items"][0]
    assert item["lane"] == "research"
    assert item["evidence_code"] == "old_analysis"


@pytest.mark.parametrize("kind", ["orphan_page", "structured_data_visible_content_mismatch"])
def test_historical_json_nul_does_not_break_preview(client, kind):
    site, url, _ = setup_site()
    with SessionLocal() as db:
        record = db.scalar(select(Issue).where(Issue.website_id == site))
        record.issue_type = kind
        snapshot = db.scalar(select(UrlSnapshot).where(UrlSnapshot.url_id == url))
        snapshot.metadata_hash = "full"
        occurrence = db.scalar(select(IssueOccurrence).where(IssueOccurrence.issue_id == record.id))
        occurrence.evidence = {
            "unrelated": "titel\x00vervolg",
            "root_route_checked": True,
            "comparison_version": 3,
        }
        db.commit()
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.get(f"/api/v1/websites/{site}/work-preview")
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert response.status_code == 200
    assert response.json()["items"][0]["current_evidence"] is True
    # Database-side JSON extraction was the production failure, including keys
    # outside the malformed string. Require raw JSON text for all preview reads.
    assert not any("JSON_EXTRACT" in statement or "->>" in statement for statement in statements)
    with SessionLocal() as db:
        record = db.scalar(select(IssueOccurrence).where(IssueOccurrence.issue_id == record.id))
        assert record.evidence["unrelated"] == "titel\x00vervolg"


def test_postgres_escaped_nul_reading():
    """Exercise the actual PostgreSQL JSON behavior; optional locally, required in CI."""
    import json
    import os

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from app.services.work_preview import read_evidence

    url = os.environ.get("WORK_PREVIEW_POSTGRES_URL")
    if not url:
        pytest.skip("Dedicated PostgreSQL regression database not configured")
    postgres = create_engine(url)
    occurrence_id = uuid4()
    payload = {"unrelated": "titel\x00vervolg", "root_route_checked": True, "comparison_version": 3}
    try:
        with postgres.connect() as connection, connection.begin():
            connection.execute(
                text("CREATE TEMP TABLE issue_occurrences (id uuid, evidence json) ON COMMIT DROP")
            )
            connection.execute(
                text("INSERT INTO issue_occurrences VALUES (:id, CAST(:payload AS json))"),
                {"id": occurrence_id, "payload": json.dumps(payload)},
            )
            with Session(bind=connection) as db:
                assert dict(read_evidence(db, [occurrence_id])) == {occurrence_id: payload}
    finally:
        postgres.dispose()


def test_duplicate_group_preserves_counts_members_search_and_pagination(client):
    site, url_id, run_id = setup_site()
    with SessionLocal() as db:
        first = db.scalar(select(Issue).where(Issue.website_id == site))
        first.issue_type = "duplicate_meta_description"
        other = Url(website_id=site, normalized_url="https://www.human.nl/second")
        db.add(other)
        db.flush()
        second = issue("duplicate_meta_description")
        second.website_id, second.url_id, second.category = site, other.id, "onpage"
        db.add(second)
        db.flush()
        first_occurrence = db.scalar(
            select(IssueOccurrence).where(IssueOccurrence.issue_id == first.id)
        )
        first_occurrence.evidence = {"value": "Shared", "related_urls": [other.normalized_url]}
        db.add(
            IssueOccurrence(
                issue_id=second.id,
                crawl_run_id=run_id,
                evidence={"value": "Shared", "related_urls": ["https://www.human.nl/page"]},
            )
        )
        # Both lack suitable content evidence and must stay in research.
        first_occurrence.snapshot_id = None
        second_id = second.id
        db.commit()
    root = f"/api/v1/websites/{site}/work-preview"
    data = client.get(root, params={"q": "second", "limit": 1}).json()
    assert data["total"] == 1
    assert data["total_signals"] == 2
    assert data["counts"]["research"] == 2
    assert len(data["items"][0]["members"]) == 2
    assert client.get(root, params={"offset": 1}).json()["items"] == []
    with SessionLocal() as db:
        db.get(Issue, second_id).status = "review"
        db.commit()
    assert client.get(root).json()["total"] == 2


@pytest.mark.parametrize("difference", ["value", "crawl", "missing", "one_way"])
def test_duplicate_groups_require_reciprocal_identical_evidence(difference):
    from types import SimpleNamespace

    from app.services.work_preview_groups import group_duplicates

    base = dict(
        issue_type="duplicate_title",
        lane="research",
        status="new",
        severity="high",
        evidence_code="old",
        reason="Review",
        first_step="Compare",
        completion="Decided",
        tasks=[],
    )
    items = [
        dict(base, issue_id=1, url="https://example.com/a"),
        dict(base, issue_id=2, url="https://example.com/b"),
    ]
    evidence = {i: SimpleNamespace(id=i, crawl_run_id=1) for i in [1, 2]}
    details = {
        1: {"value": "Same", "related_urls": [items[1]["url"]]},
        2: {"value": "Same", "related_urls": [items[0]["url"]]},
    }
    if difference == "value":
        details[2]["value"] = "Different"
    elif difference == "crawl":
        evidence[2].crawl_run_id = 2
    elif difference == "missing":
        details[2] = {}
    else:
        details[2]["related_urls"] = ["https://example.com/c"]
    assert len(group_duplicates(items, evidence, details)) == 2


def test_task_detail_uses_same_review_as_preview(client):
    site, _, _ = setup_site()
    with SessionLocal() as db:
        record = db.scalar(select(Issue).where(Issue.website_id == site))
        record.issue_type = "internally_linked_redirect"
        record.status = "review"
        record_id = record.id
        db.commit()
    response = client.post(f"/api/v1/issues/{record_id}/recommendation-task")
    assert response.status_code == 201
    task_id = response.json()["id"]
    detail = client.get(f"/api/v1/recommendation-tasks/{task_id}").json()
    card = client.get(f"/api/v1/websites/{site}/work-preview").json()["items"][0]
    assert detail["readiness"]["lane"] == card["lane"] == "research"
    assert detail["readiness"]["first_step"] == card["first_step"]
    assert detail["readiness"]["reason"] == card["reason"]

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.issues import Issue
from app.models.rendering import RenderObservation
from app.models.website import Website, WebsiteSettings
from app.services.browser_renderer import BrowserRenderResult
from app.services.render_executor import execute_render_observation


def test_executor_stores_comparison_and_reconciles_issues(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    with SessionLocal() as db:
        observation = _observation(db)
        observation_id = str(observation.id)
        db.commit()

    monkeypatch.setattr(
        "app.services.render_executor.render_page_html",
        lambda _url: BrowserRenderResult(
            html=(
                "<html><body><main>"
                + ("rendered woord " * 180)
                + '<a href="/dynamic">Dynamisch</a></main></body></html>'
            ),
            browser_name="chromium",
            request_count=7,
            element_boxes=[
                {"element_id": "cta", "x": 1, "y": 2, "width": 3, "height": 4}
            ],
        ),
    )

    execute_render_observation(observation_id)

    with SessionLocal() as db:
        stored = db.get(RenderObservation, observation.id)
        issues = set(db.scalars(select(Issue.issue_type)))
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.rendered_at is not None
        assert stored.comparison["browser_request_count"] == 7
        assert stored.comparison["screenshot_element_boxes"][0]["element_id"] == "cta"
        assert stored.comparison["javascript_dependent_content"] is True
        assert "javascript_dependent_content" in issues
        assert "javascript_only_links" in issues


def test_executor_persists_failure_for_retry(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    with SessionLocal() as db:
        observation = _observation(db)
        observation_id = str(observation.id)
        db.commit()

    monkeypatch.setattr(
        "app.services.render_executor.render_page_html",
        lambda _url: (_ for _ in ()).throw(RuntimeError("browser stopped")),
    )

    try:
        execute_render_observation(observation_id)
    except RuntimeError:
        pass

    with SessionLocal() as db:
        stored = db.get(RenderObservation, observation.id)
        assert stored is not None
        assert stored.status == "failed"
        assert stored.error_message == "RuntimeError: browser stopped"


def test_executor_passes_inspection_focus_to_renderer(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    with SessionLocal() as db:
        observation = _observation(db)
        observation.comparison = {
            "inspection_focus": {"strategy": "id", "value": "cta"}
        }
        observation_id = str(observation.id)
        db.commit()

    received: list[dict[str, object]] = []

    def render(_url: str, **kwargs: object) -> BrowserRenderResult:
        received.append(kwargs)
        return BrowserRenderResult(
            html="<html><body><button id='cta'>Actie</button></body></html>",
            browser_name="chromium",
            request_count=1,
            focus_status="focused",
        )

    monkeypatch.setattr("app.services.render_executor.render_page_html", render)
    execute_render_observation(observation_id)

    with SessionLocal() as db:
        stored = db.get(RenderObservation, observation.id)
        assert received == [{"focus_target": {"strategy": "id", "value": "cta"}}]
        assert stored is not None
        assert stored.comparison["inspection_focus_applied"] is True
        assert stored.comparison["inspection_focus_status"] == "focused"


def test_executor_checks_if_missing_element_is_live_present(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    with SessionLocal() as db:
        observation = _observation(db)
        observation.comparison = {"inspection_absence": {"element_type": "h1"}}
        observation_id = str(observation.id)
        db.commit()

    monkeypatch.setattr(
        "app.services.render_executor.render_page_html",
        lambda _url: BrowserRenderResult(
            html="<html><body><h1>Nieuwe kop</h1></body></html>",
            browser_name="chromium",
            request_count=1,
        ),
    )
    execute_render_observation(observation_id)

    with SessionLocal() as db:
        stored = db.get(RenderObservation, observation.id)
        assert stored is not None
        assert stored.comparison["inspection_absence"] == {"element_type": "h1"}
        assert stored.comparison["inspection_absence_status"] == "present"


def test_executor_reconciles_requested_accessibility_results(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    with SessionLocal() as db:
        observation = _observation(db)
        observation.comparison = {"accessibility_requested": True}
        observation_id = str(observation.id)
        db.commit()

    received: list[dict[str, object]] = []

    def render(_url: str, **kwargs: object) -> BrowserRenderResult:
        received.append(kwargs)
        return BrowserRenderResult(
            html="<html lang='nl'><head><title>Test</title></head><body></body></html>",
            browser_name="chromium",
            request_count=1,
            accessibility_result={
                "testEngine": {"version": "4.12.1"},
                "violations": [
                    {
                        "id": "button-name",
                        "impact": "critical",
                        "nodes": [{"target": ["#buy"], "html": "<button id='buy'></button>"}],
                    }
                ],
                "incomplete": [],
            },
        )

    monkeypatch.setattr("app.services.render_executor.render_page_html", render)
    execute_render_observation(observation_id)

    with SessionLocal() as db:
        stored = db.get(RenderObservation, observation.id)
        issue = db.scalar(select(Issue).where(Issue.issue_type == "accessibility_button_name"))
        assert received == [{"run_accessibility": True}]
        assert stored is not None
        assert stored.comparison["accessibility"]["engine_version"] == "4.12.1"
        assert issue is not None
        assert issue.category == "accessibility"


def _observation(db) -> RenderObservation:  # type: ignore[no-untyped-def]
    website = Website(
        client=Client(name="Render client"),
        name="Render site",
        base_url="https://example.com/",
    )
    website.settings = WebsiteSettings()
    db.add(website)
    db.flush()
    url = Url(
        website_id=website.id,
        normalized_url="https://example.com/app",
        is_active=True,
        is_indexable=True,
    )
    job = CrawlJob(website_id=website.id, job_type="full_site_crawl")
    db.add_all([url, job])
    db.flush()
    run = CrawlRun(
        crawl_job_id=job.id,
        website_id=website.id,
        crawl_type="full_site_crawl",
    )
    db.add(run)
    db.flush()
    snapshot = UrlSnapshot(
        url_id=url.id,
        crawl_run_id=run.id,
        requested_url=url.normalized_url,
        final_url=url.normalized_url,
        status_code=200,
        content_type="text/html",
        is_indexable=True,
        word_count=5,
        main_content="lege app shell",
        main_content_hash="static-main",
        metadata_hash="static-meta",
        links_hash="static-links",
        schema_hash="static-schema",
    )
    db.add(snapshot)
    db.flush()
    observation = RenderObservation(
        website_id=website.id,
        url_id=url.id,
        source_snapshot_id=snapshot.id,
        status="pending",
        trigger_reasons=["low_static_word_count"],
    )
    db.add(observation)
    db.flush()
    return observation

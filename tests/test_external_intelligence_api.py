from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

from app.db.session import SessionLocal
from app.models.crawl import CrawlRun, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.external_intelligence import (
    ExternalIntelligenceRequest,
    ExternalObservation,
)
from app.models.website import WebsiteSettings


def create_website(client) -> str:  # type: ignore[no-untyped-def]
    customer = client.post("/api/v1/clients", json={"name": "Evidence client"}).json()
    return client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": "Evidence site",
            "base_url": "https://evidence.example",
        },
    ).json()["id"]


def payload() -> dict[str, object]:
    return {
        "capability": "ai_citations",
        "question": "wat kosten kunststof kozijnen",
        "language": "nl",
        "country": "NL",
        "device": "mobile",
    }


def enable_website(website_id: str, *, budget: int = 10_000) -> None:
    with SessionLocal() as db:
        settings = db.get(WebsiteSettings, UUID(website_id))
        assert settings is not None
        settings.external_intelligence_enabled = True
        settings.external_monthly_budget_micros = budget
        settings.external_active_scope_limit = 5
        db.commit()


def enable_global(monkeypatch, *, estimate: int = 800) -> None:  # type: ignore[no-untyped-def]
    from app.api.routes import content_analysis

    monkeypatch.setattr(
        content_analysis,
        "get_settings",
        lambda: SimpleNamespace(
            dataforseo_enabled=True,
            external_serp_estimated_cost_micros=500,
            external_ai_citations_estimated_cost_micros=estimate,
        ),
    )


def test_external_evidence_is_unavailable_by_default(client) -> None:  # type: ignore[no-untyped-def]
    website_id = create_website(client)

    response = client.post(
        f"/api/v1/websites/{website_id}/content-analysis/external-evidence",
        json=payload(),
    )

    assert response.status_code == 503
    assert "provider" not in response.text.lower()
    with SessionLocal() as db:
        assert db.query(ExternalIntelligenceRequest).count() == 0


def test_human_selection_enqueues_once_and_response_hides_provider(
    client, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    from app.api.routes import content_analysis

    website_id = create_website(client)
    enable_website(website_id)
    enable_global(monkeypatch)
    enqueued: list[str] = []
    monkeypatch.setattr(
        content_analysis,
        "enqueue_external_intelligence",
        lambda request_id, **_kwargs: enqueued.append(request_id) or True,
    )

    endpoint = f"/api/v1/websites/{website_id}/content-analysis/external-evidence"
    first = client.post(endpoint, json=payload())
    duplicate = client.post(endpoint, json=payload())
    status = client.get(f"{endpoint}/{first.json()['request_id']}")

    assert first.status_code == 202 and first.json()["status"] == "queued"
    assert duplicate.status_code == 202 and duplicate.json()["status"] == "pending"
    assert status.status_code == 200 and status.json()["status"] == "pending"
    assert len(enqueued) == 1
    for response in (first, duplicate, status):
        assert "provider" not in response.text.lower()
        assert "cost" not in response.text.lower()


def test_budget_is_checked_before_enqueue(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.api.routes import content_analysis

    website_id = create_website(client)
    enable_website(website_id, budget=500)
    enable_global(monkeypatch, estimate=800)
    enqueued: list[str] = []
    monkeypatch.setattr(
        content_analysis,
        "enqueue_external_intelligence",
        lambda request_id, **_kwargs: enqueued.append(request_id) or True,
    )

    response = client.post(
        f"/api/v1/websites/{website_id}/content-analysis/external-evidence",
        json=payload(),
    )

    assert response.status_code == 202
    assert response.json() == {
        "request_id": None,
        "observation_id": None,
        "status": "budget_exceeded",
        "capability": "ai_citations",
    }
    assert enqueued == []


def test_queue_rejection_cancels_reserved_request(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.api.routes import content_analysis

    website_id = create_website(client)
    enable_website(website_id)
    enable_global(monkeypatch)
    monkeypatch.setattr(
        content_analysis, "enqueue_external_intelligence", lambda *_args, **_kwargs: False
    )

    response = client.post(
        f"/api/v1/websites/{website_id}/content-analysis/external-evidence",
        json=payload(),
    )

    assert response.status_code == 503
    with SessionLocal() as db:
        request = db.query(ExternalIntelligenceRequest).one()
        assert request.status == "cancelled"
        assert request.finished_at is not None


def test_completed_evidence_exposes_only_user_relevant_result(
    client, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    from app.api.routes import content_analysis

    website_id = create_website(client)
    enable_website(website_id)
    enable_global(monkeypatch)
    monkeypatch.setattr(
        content_analysis, "enqueue_external_intelligence", lambda *_args, **_kwargs: True
    )
    with SessionLocal() as db:
        url = Url(
            website_id=UUID(website_id),
            normalized_url="https://evidence.example/kunststof-kozijnen",
            current_status_code=200,
            is_active=True,
            is_indexable=True,
        )
        db.add(url)
        db.flush()
        job = CrawlJob(website_id=UUID(website_id), job_type="full_site_crawl")
        db.add(job)
        db.flush()
        run = CrawlRun(
            crawl_job_id=job.id,
            website_id=UUID(website_id),
            crawl_type="full_site_crawl",
        )
        db.add(run)
        db.flush()
        db.add(
            UrlSnapshot(
                url_id=url.id,
                crawl_run_id=run.id,
                requested_url=url.normalized_url,
                final_url=url.normalized_url,
                status_code=200,
                content_type="text/html",
                title="Kunststof kozijnen",
                headings={"h1": ["Kunststof kozijnen"]},
                main_content="Wij leveren isolerende kozijnen in verschillende kleuren.",
                word_count=80,
                is_indexable=True,
            )
        )
        db.commit()
        url_id = str(url.id)
    endpoint = f"/api/v1/websites/{website_id}/content-analysis/external-evidence"
    request_payload = {**payload(), "url_id": url_id}
    created = client.post(endpoint, json=request_payload)
    request_id = created.json()["request_id"]
    observed_at = datetime(2026, 8, 8, 9, 30, tzinfo=UTC)

    with SessionLocal() as db:
        request = db.get(ExternalIntelligenceRequest, UUID(request_id))
        assert request is not None
        request.status = "succeeded"
        request.actual_cost_micros = 1234
        request.finished_at = observed_at
        observation = ExternalObservation(
            website_id=UUID(website_id),
            request_id=request.id,
            capability="ai_citations",
            cache_key=request.cache_key,
            provider="dataforseo",
            observed_at=observed_at,
            expires_at=observed_at + timedelta(days=7),
            input_hash="a" * 64,
            evidence_hash="b" * 64,
            normalized_payload={
                "observations": [
                    {
                        "observed_at": observed_at.isoformat(),
                        "observed_question": "Wat kosten kunststof kozijnen?",
                        "sources": [
                            {
                                "url": "https://example.com/kozijnen",
                                "title": "Kosten van kunststof kozijnen",
                                "position": 1,
                            }
                        ],
                        "answer_excerpt": "Dit antwoord mag niet zichtbaar zijn.",
                        "warnings": ["interne technische melding"],
                    }
                ]
            },
            source_coverage={"citation_count": 1, "provider": "dataforseo"},
        )
        db.add(observation)
        db.commit()
        observation_id = str(observation.id)

    status = client.get(f"{endpoint}/{request_id}")
    result = client.get(f"{endpoint}/observations/{observation_id}")

    assert status.status_code == 200
    assert status.json()["observation_id"] == observation_id
    assert result.status_code == 200
    assert result.json()["question"] == payload()["question"]
    assert result.json()["assessment"]["status"] == "observed_citation_gap"
    assert result.json()["assessment"]["coverage_status"] == "missing"
    assert result.json()["assessment"]["recommended_action"]
    assert result.json()["observations"][0]["observed_question"] == (
        "Wat kosten kunststof kozijnen?"
    )
    assert result.json()["observations"][0]["sources"][0]["url"] == (
        "https://example.com/kozijnen"
    )
    hidden = result.text.lower()
    for internal_value in (
        "dataforseo",
        "provider",
        "cost",
        "answer_excerpt",
        "dit antwoord mag niet zichtbaar zijn",
        "interne technische melding",
    ):
        assert internal_value not in hidden

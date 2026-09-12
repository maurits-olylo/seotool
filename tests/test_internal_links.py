from datetime import timedelta

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.common import utc_now
from app.models.crawl import CrawlRun, UrlLink, UrlSnapshot
from app.models.discovery import CrawlJob, Url
from app.models.website import Website


def fixture() -> dict:
    with SessionLocal() as db:
        website = Website(
            client=Client(name="Links"), name="Links", base_url="https://example.test"
        )
        other = Website(client=Client(name="Other"), name="Other", base_url="https://other.test")
        db.add_all([website, other])
        db.flush()
        urls = [
            Url(website_id=website.id, normalized_url=f"https://example.test/{name}")
            for name in ("a", "b", "target", "zero")
        ]
        outsider = Url(website_id=other.id, normalized_url="https://other.test/")
        db.add_all([*urls, outsider])
        db.flush()
        runs = []
        for days, kind, status in (
            (3, "full_site_crawl", "succeeded"),
            (2, "full_site_crawl", "succeeded"),
            (1, "light_check", "succeeded"),
            (0, "full_site_crawl", "failed"),
        ):
            job = CrawlJob(website_id=website.id, job_type=kind, status=status)
            db.add(job)
            db.flush()
            run = CrawlRun(
                crawl_job_id=job.id,
                website_id=website.id,
                crawl_type=kind,
                status=status,
                started_at=utc_now() - timedelta(days=days, hours=1),
                finished_at=utc_now() - timedelta(days=days),
            )
            db.add(run)
            db.flush()
            runs.append(run)
            for url in urls:
                db.add(
                    UrlSnapshot(
                        url_id=url.id,
                        crawl_run_id=run.id,
                        requested_url=url.normalized_url,
                        status_code=200 if days != 1 else 404,
                    )
                )
        a, b, target, zero = urls
        for run, source, destination, anchor, internal, nofollow in (
            (runs[0], a, target, "Old", True, False),
            (runs[1], a, target, "First", True, False),
            (runs[1], a, target, "Second", True, False),
            (runs[1], b, target, "Nofollow", True, True),
            (runs[1], target, target, "Self", True, False),
            (runs[1], outsider, target, "Other site", True, False),
            (runs[1], a, outsider, "External", False, False),
            (runs[2], zero, target, "Light", True, False),
            (runs[3], zero, target, "Failed", True, False),
        ):
            db.add(
                UrlLink(
                    crawl_run_id=run.id,
                    source_url_id=source.id,
                    target_url_id=destination.id,
                    target_url=destination.normalized_url,
                    anchor_text=anchor,
                    is_internal=internal,
                    is_nofollow=nofollow,
                )
            )
        db.commit()
        return {
            "website": str(website.id),
            "target": str(target.id),
            "other": str(other.id),
            "run": str(runs[1].id),
            "light": str(runs[2].id),
        }


def test_ranking_uses_unique_sources_and_completed_full_crawl(client):
    ids = fixture()
    response = client.get(f"/api/v1/websites/{ids['website']}/internal-links")
    assert response.status_code == 200
    data = response.json()
    assert data["crawl_run_id"] == ids["run"]
    assert data["total"] == 4
    assert data["top"][0]["incoming_pages"] == 2
    assert data["top"][0]["change"] == 1
    assert data["top"][0]["status_code"] == 200
    assert data["top"][0]["url_id"] == ids["target"]
    assert len(data["top"]) == 1


def test_sources_preserve_run_and_group_anchor_texts(client):
    ids = fixture()
    base = f"/api/v1/websites/{ids['website']}/internal-links/{ids['target']}/sources"
    data = client.get(base, params={"crawl_run_id": ids["run"], "limit": 1}).json()
    assert data["total"] == 2
    assert data["items"] == [{"url": "https://example.test/a", "anchor_texts": ["First", "Second"]}]
    assert client.get(base, params={"crawl_run_id": ids["light"]}).status_code == 404
    cross = base.replace(ids["website"], ids["other"])
    assert client.get(cross, params={"crawl_run_id": ids["run"]}).status_code == 404


def test_search_sort_pagination_and_auth(client):
    ids = fixture()
    url = f"/api/v1/websites/{ids['website']}/internal-links"
    data = client.get(url, params={"q": "ZERO"}).json()
    assert data["total"] == 1 and data["items"][0]["incoming_pages"] == 0
    data = client.get(url, params={"order": "links_asc", "limit": 1, "offset": 3}).json()
    assert data["items"][0]["url_id"] == ids["target"]
    assert client.get(url, headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get(url, params={"limit": 101}).status_code == 422
    assert (
        client.get(f"/api/v1/websites/{ids['other']}/internal-links").json()["crawl_run_id"] is None
    )


def test_expired_history_is_not_reported_as_zero_change(client) -> None:
    ids = fixture()
    with SessionLocal() as db:
        # Make all full crawls older than retention, including the earlier successful run.
        from sqlalchemy import select

        for full in db.scalars(select(CrawlRun).where(CrawlRun.crawl_type == "full_site_crawl")):
            full.started_at = utc_now() - timedelta(days=181)
            full.finished_at = utc_now() - timedelta(days=180)
        db.commit()
    data = client.get(f"/api/v1/websites/{ids['website']}/internal-links").json()
    assert data["crawl_run_id"] is None
    assert "bewaartermijn" in data["reason"]


def test_membership_required_for_link_data(client) -> None:
    from uuid import uuid4

    from app.core.security import Principal, require_api_key
    from app.main import app

    ids = fixture()
    app.dependency_overrides[require_api_key] = lambda: Principal(
        user_id=uuid4(),
        role="user",
        is_api_key=False,
    )
    try:
        response = client.get(f"/api/v1/websites/{ids['website']}/internal-links")
        assert response.status_code in {403, 404}
    finally:
        app.dependency_overrides.pop(require_api_key)


def test_review_labels_boundaries_and_technical_errors() -> None:
    from app.services.internal_links import classify_items

    def item(path, count, status=200, change=0):
        return dict(
            url=f"https://example.test{path}",
            incoming_pages=count,
            status_code=status,
            change=change,
        )

    rows = [
        item("/menu", 8),
        item("/content", 7),
        item("/few", 2),
        item("/unknown", 0, None),
        item("/admin-panel/forms/save", 9, 500),
        item("/lost", 4, 200, -3),
        item("/apiary", 0),
    ]
    summary = classify_items(rows, 10)
    assert summary == dict(attention=4, low=2, lost=1, errors=1, repeated=2, technical=1)
    assert "repeated" in rows[0]["signals"] and "repeated" not in rows[1]["signals"]
    assert rows[3]["signals"] == []
    assert {"technical", "errors", "attention"} <= set(rows[4]["signals"])
    assert "technical" not in rows[6]["signals"]
    classify_items(rows, 9)
    assert all("repeated" not in row["signals"] for row in rows)


def test_review_filters_and_summary_are_independent_of_search(client) -> None:
    ids = fixture()
    url = f"/api/v1/websites/{ids['website']}/internal-links"
    data = client.get(
        url, params={"view": "low", "q": "zero", "limit": 5, "order": "priority"}
    ).json()
    assert data["total"] == 1
    assert data["summary"]["low"] == 4
    assert "low" in data["items"][0]["signals"]
    assert client.get(url, params={"view": "errors"}).json()["total"] == 0
    assert client.get(url, params={"view": "technical"}).json()["total"] == 0
    assert client.get(url, params={"view": "invalid"}).status_code == 422

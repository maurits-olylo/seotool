import pytest

from app.api.routes import integrations


@pytest.mark.parametrize(
    ("path", "service"),
    [
        ("search_console", "search_console"),
        ("ga4", "ga4"),
        ("matomo", "matomo"),
        ("bing_webmaster", "bing_webmaster"),
    ],
)
def test_manual_integration_sync_is_queued(client, monkeypatch, path: str, service: str) -> None:  # type: ignore[no-untyped-def]
    customer = client.post("/api/v1/clients", json={"name": f"Queue {service}"}).json()
    website = client.post(
        "/api/v1/websites",
        json={
            "client_id": customer["id"],
            "name": f"Queue {service}",
            "base_url": "https://example.com",
        },
    ).json()
    captured: list[tuple[object, ...]] = []
    monkeypatch.setattr(integrations, "queue_has_capacity", lambda _queue: True)
    monkeypatch.setattr(
        integrations,
        "enqueue_integration_sync",
        lambda *args, **_kwargs: captured.append(args) or True,
    )

    response = client.post(f"/api/v1/websites/{website['id']}/integrations/{path}/sync")

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert captured[0][2] == [service]
